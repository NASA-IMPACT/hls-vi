# pyright: reportAttributeAccessIssue=false
# pyright: reportOperatorIssue=false
# pyright: reportOptionalOperand=false

import getopt
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from enum import Enum, unique
from pathlib import Path
from typing import Callable, List, Mapping, Optional, SupportsFloat, Tuple, Type
from typing_extensions import TypeAlias

import numpy as np
import rasterio
import rasterio.crs
import rasterio.transform

from dataclasses import dataclass


Tags: TypeAlias = Mapping[str, Optional[str]]
BandData: TypeAlias = Mapping["Band", np.ma.masked_array]
IndexFunction = Callable[[BandData], np.ma.masked_array]

fixed_tags = (
    "add_offset",
    "ACCODE",
    "AREA_OR_POINT",
    "cloud_coverage",
    "HORIZONTAL_CS_NAME",
    "MEAN_SUN_AZIMUTH_ANGLE",
    "MEAN_SUN_ZENITH_ANGLE",
    "MEAN_VIEW_AZIMUTH_ANGLE",
    "MEAN_VIEW_ZENITH_ANGLE",
    "NBAR_SOLAR_ZENITH",
    "NCOLS",
    "NROWS",
    "SENSING_TIME",
    "spatial_coverage",
    "SPATIAL_RESOLUTION",
    "ULX",
    "ULY",
)


@unique
class Band(Enum):
    B = "B"
    G = "G"
    R = "R"
    NIR = "NIR"
    SWIR1 = "SWIR1"
    SWIR2 = "SWIR2"


class InstrumentBand(Enum):
    pass


@unique
class L30Band(InstrumentBand):
    B02 = Band.B
    B03 = Band.G
    B04 = Band.R
    B05 = Band.NIR
    B06 = Band.SWIR1
    B07 = Band.SWIR2


@unique
class S30Band(InstrumentBand):
    B02 = Band.B
    B03 = Band.G
    B04 = Band.R
    B8A = Band.NIR
    B11 = Band.SWIR1
    B12 = Band.SWIR2


class Instrument(Enum):
    # Example LANDSAT_PRODUCT_ID: LC08_L1TP_069014_20240429_20240430_02_RT
    # Pull out satellite number ("08"), convert to an integer, and prepend "L" to get
    # the satellite name.
    L30 = L30Band, lambda tags: f"L{int(tags.get('LANDSAT_PRODUCT_ID', '')[2:4])}"
    # Example PRODUCT_URI: S2B_MSIL1C_...
    # Simply pull off the first part of the string before the first underscore to get
    # the satellite name.
    S30 = S30Band, lambda tags: tags.get("PRODUCT_URI", "").split("_")[0]

    def __init__(
        self, band_type: Type[InstrumentBand], parse_satellite: Callable[[Tags], str]
    ) -> None:
        self.bands: List[InstrumentBand] = list(band_type)
        self.parse_satellite = parse_satellite

    @classmethod
    def named(cls, name: str) -> "Instrument":
        for instrument in cls:
            if instrument.name == name:
                return instrument

        raise ValueError(f"Invalid instrument name: {name}")

    def satellite(self, tags: Tags) -> str:
        return self.parse_satellite(tags)


@dataclass
class GranuleId:
    instrument: Instrument
    tile_id: str
    acquisition_date: str
    version: str

    @classmethod
    def from_string(cls, granule_id: str) -> "GranuleId":
        # Assume granule_id is formatted as follows, where {version} may contain dots:
        # HLS.{instrument}.{tile_id}.{acquisition_date}.{version}
        match = re.match(
            r"HLS[.](?P<instrument>[^.]+)[.](?P<tile_id>[^.]+)[.]"
            r"(?P<acquisition_date>[^.]+)[.](?P<version>.+)",
            granule_id,
        )

        if not match:
            raise ValueError(f"Invalid granule ID: {granule_id}")

        return GranuleId(
            Instrument.named(match["instrument"]),
            match["tile_id"],
            match["acquisition_date"],
            match["version"],
        )

    def __str__(self) -> str:
        return ".".join(
            [
                "HLS",
                self.instrument.name,
                self.tile_id,
                self.acquisition_date,
                self.version,
            ]
        )


@dataclass
class Granule:
    id_: GranuleId
    crs: rasterio.crs.CRS
    transform: rasterio.transform.Affine
    tags: Tags
    data: BandData


def read_granule_bands(input_dir: Path, id_str: str) -> Granule:
    id_ = GranuleId.from_string(id_str)

    with rasterio.open(input_dir / f"{id_}.Fmask.tif") as tif:
        fmask = tif.read(1, masked=False)

    tifnames = [f"{id_}.{band.name}.tif" for band in id_.instrument.bands]
    data = [apply_fmask(read_band(input_dir / tifname), fmask) for tifname in tifnames]
    harmonized_bands = [band.value for band in id_.instrument.bands]

    # Every band has the same CRS, transform, and tags, so we can use the first one to
    # get this information.
    with rasterio.open(input_dir / tifnames[0]) as tif:
        crs = tif.crs
        transform = tif.transform
        tags = select_tags(id_, tif.tags())

    return Granule(id_, crs, transform, tags, dict(zip(harmonized_bands, data)))


def read_band(tif_path: Path) -> np.ma.masked_array:
    with rasterio.open(tif_path) as tif:
        data = tif.read(1, masked=True, fill_value=-9999) / 10_000

    # Clamp surface reflectance values to the range [0.0001, ∞]
    # * We consider 0% reflectance to be invalid data
    # * We want to retain values >100% reflectance. This is a known issue with
    #   atmospheric compensation where it's possible to have values >100% reflectance
    #   due to unmet assumptions about topography.
    # See, https://github.com/NASA-IMPACT/hls-vi/issues/44#issuecomment-2520592212
    return np.ma.masked_less_equal(data, 0)


def apply_fmask(data: np.ndarray, fmask: np.ndarray) -> np.ma.masked_array:
    # Per Table 9 in https://lpdaac.usgs.gov/documents/1698/HLS_User_Guide_V2.pdf
    # we wish to mask data where the Fmask has any one of the following bits set:
    # cloud shadow (bit 3), adjacent to cloud/shadow (bit 2), cloud (bit 1).
    cloud_like = int("00001110", 2)
    return np.ma.masked_array(data, fmask & cloud_like != 0)


def apply_union_of_masks(bands: list[np.ma.masked_array]) -> list[np.ma.masked_array]:
    """Mask all bands according to valid data across all bands

    This is intended to reduce noise by masking spectral indices if
    any reflectance band is outside of expected range of values ([1, 10000]).
    For example the NBR index only looks at NIR and SWIR bands, but we might have
    negative reflectance in visible bands that indicate the retrieval has issues
    and should not be used.

    Reference: https://github.com/NASA-IMPACT/hls-vi/issues/44
    """
    if not bands:
        return []

    # NB - numpy masked arrays "true" is a masked value, "false" is unmasked
    # so bitwise "or" will  mask if "any" band has a masked value for that pixel
    mask = bands[0].mask.copy()
    for band in bands[1:]:
        mask |= band.mask

    for band in bands:
        band.mask = mask
    return bands


def select_tags(granule_id: GranuleId, tags: Tags) -> Tags:
    """
    Selects tags from the input tags that are relevant to the HLS VI product.

    Args:
        tags: Mapping of tags from an instrument band image.

    Returns:
        Mapping of relevant VI tags.
    """
    return {
        **{tag: tags.get(tag) for tag in fixed_tags},
        "MGRS_TILE_ID": granule_id.tile_id,
        "SATELLITE": granule_id.instrument.satellite(tags),
    }


def write_granule_indices(output_dir: Path, granule: Granule) -> None:
    os.makedirs(output_dir, exist_ok=True)
    processing_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    for index in Index:
        output_path = output_dir / ".".join(
            [
                "HLS-VI",
                granule.id_.instrument.name,
                granule.id_.tile_id,
                granule.id_.acquisition_date,
                granule.id_.version,
                index.name,
                "tif",
            ]
        )

        write_granule_index(output_path, granule, index, processing_time)


def write_granule_index(
    output_path: Path,
    granule: Granule,
    index: "Index",
    processing_time: str,
) -> None:
    """Save raster data to a GeoTIFF file using rasterio."""

    data = index(granule.data)

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        compress="deflate",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs=granule.crs,
        transform=granule.transform,
        nodata=index.fill_value,
    ) as dst:
        dst.offsets = (0.0,)
        dst.scales = (index.scale_factor,)
        dst.write(data.filled(fill_value=index.fill_value), 1)
        dst.update_tags(
            **granule.tags,
            long_name=index.long_name,
            scale_factor=index.scale_factor,
            HLS_VI_PROCESSING_TIME=processing_time,
            _FillValue=data.fill_value,
        )


def evi(data: BandData) -> np.ma.masked_array:
    b, r, nir = data[Band.B], data[Band.R], data[Band.NIR]
    return 2.5 * (nir - r) / (nir + 6 * r - 7.5 * b + 1)


def msavi(data: BandData) -> np.ma.masked_array:
    r, nir = data[Band.R], data[Band.NIR]
    sqrt_term = (2 * nir + 1) ** 2 - 8 * (nir - r)

    result: np.ma.masked_array = np.ma.where(
        sqrt_term >= 0,
        (2 * nir + 1 - np.sqrt(sqrt_term)) / 2,
        np.nan,
    )
    result.fill_value = r.fill_value

    return result


def nbr(data: BandData) -> np.ma.masked_array:
    nir, swir2 = data[Band.NIR], data[Band.SWIR2]
    return (nir - swir2) / (nir + swir2)


def nbr2(data: BandData) -> np.ma.masked_array:
    swir1, swir2 = data[Band.SWIR1], data[Band.SWIR2]
    return (swir1 - swir2) / (swir1 + swir2)


def ndmi(data: BandData) -> np.ma.masked_array:
    nir, swir1 = data[Band.NIR], data[Band.SWIR1]
    return (nir - swir1) / (nir + swir1)


def ndvi(data: BandData) -> np.ma.masked_array:
    r, nir = data[Band.R], data[Band.NIR]
    return (nir - r) / (nir + r)


def ndwi(data: BandData) -> np.ma.masked_array:
    g, nir = data[Band.G], data[Band.NIR]
    return (g - nir) / (g + nir)


def savi(data: BandData) -> np.ma.masked_array:
    r, nir = data[Band.R], data[Band.NIR]
    return 1.5 * (nir - r) / (nir + r + 0.5)


def tvi(data: BandData) -> np.ma.masked_array:
    g, r, nir = data[Band.G], data[Band.R], data[Band.NIR]
    return (120 * (nir - g) - 200 * (r - g)) / 2  # pyright: ignore[reportReturnType]


class Index(Enum):
    EVI = ("Enhanced Vegetation Index",)
    MSAVI = ("Modified Soil-Adjusted Vegetation Index",)
    NBR = ("Normalized Burn Ratio",)
    NBR2 = ("Normalized Burn Ratio 2",)
    NDMI = ("Normalized Difference Moisture Index",)
    NDVI = ("Normalized Difference Vegetation Index",)
    NDWI = ("Normalized Difference Water Index",)
    SAVI = ("Soil-Adjusted Vegetation Index",)
    TVI = ("Triangular Vegetation Index", 0.01)

    def __init__(self, long_name: str, scale_factor: SupportsFloat = 0.0001, fill_value: int = -19_999) -> None:
        function_name = self.name.lower()
        index_function: Optional[IndexFunction] = globals().get(function_name)

        if not index_function or not callable(index_function):
            raise ValueError(f"Index function not found: {function_name}")

        self.long_name = long_name
        self.compute_index = index_function
        self.scale_factor = float(scale_factor)
        self.fill_value = fill_value

    def __call__(self, data: BandData) -> np.ma.masked_array:
        scaled_index = self.compute_index(data) / self.scale_factor
        # We need to round to whole numbers (i.e., 0 decimal places, which is
        # the default for np.round) because we convert to integer values, but
        # numpy's conversion to integer types performs truncation, not rounding.
        return np.ma.round(scaled_index).astype(np.int16)


def parse_args() -> Tuple[Path, Path, str]:
    short_options = "i:o:s:"
    long_options = ["inputdir=", "outputdir=", "idstring="]
    command = os.path.basename(sys.argv[0])
    help_text = f"usage: {command} -i <input_dir> -o <output_dir> -s <id_string>"

    argv = sys.argv[1:]

    try:
        options, _ = getopt.getopt(argv, short_options, long_options)
    except getopt.GetoptError:
        print(help_text, file=sys.stderr)
        sys.exit(2)

    input_dir, output_dir, id_str = None, None, None

    for option, value in options:
        if option in ("-i", "--inputdir"):
            input_dir = value
        elif option in ("-o", "--outputdir"):
            output_dir = value
        elif option in ("-s", "--idstring"):
            id_str = value

    if input_dir is None or output_dir is None or id_str is None:
        print(help_text, file=sys.stderr)
        sys.exit(2)

    return Path(input_dir), Path(output_dir), id_str


def generate_vi_granule(input_dir: Path, output_dir: Path, id_str: str) -> Granule:
    granule = read_granule_bands(input_dir, id_str)
    write_granule_indices(output_dir, granule)
    shutil.copy(
        input_dir / f"{granule.id_}.jpg",
        output_dir / f"{str(granule.id_).replace('HLS', 'HLS-VI')}.jpg",
    )

    return granule


def main() -> None:
    input_dir, output_dir, id_str = parse_args()
    generate_vi_granule(input_dir, output_dir, id_str)


if __name__ == "__main__":
    main()
