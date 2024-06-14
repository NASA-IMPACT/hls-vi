# pyright: reportAttributeAccessIssue=false, reportOperatorIssue=false

import getopt
import os
import re
import sys
from datetime import datetime, timezone
from enum import Enum, unique
from pathlib import Path
from typing import Callable, Mapping, Optional, Tuple, Type
from typing_extensions import TypeAlias

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import rasterio.crs
import rasterio.transform

from dataclasses import dataclass


Tags: TypeAlias = Mapping[str, Optional[str]]
BandData: TypeAlias = Mapping["Band", np.ma.masked_array]
IndexFunction = Callable[[BandData], np.ma.masked_array]


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
    L30 = L30Band
    S30 = S30Band

    def __init__(self, band_type: Type[InstrumentBand]) -> None:
        self.bands = list(band_type)

    @classmethod
    def named(cls, name: str) -> "Instrument":
        for instrument in cls:
            if instrument.name == name:
                return instrument

        raise ValueError(f"Invalid instrument name: {name}")


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


def read_granule_bands(input_dir: Path) -> Granule:
    id_ = GranuleId.from_string(os.path.basename(input_dir))
    filenames = [f"{id_}.{band.name}.tif" for band in id_.instrument.bands]
    data = [read_band(input_dir / filename) for filename in filenames]
    harmonized_bands = [band.value for band in id_.instrument.bands]

    # Every band has the same CRS, transform, and tags, so we can use the first one to
    # get this information.
    with rasterio.open(input_dir / filenames[0]) as tif:
        crs = tif.crs
        transform = tif.transform
        tags = select_tags(tif.tags())

    return Granule(id_, crs, transform, tags, dict(zip(harmonized_bands, data)))


def read_band(tif_path: Path) -> np.ma.masked_array:
    with rasterio.open(tif_path) as tif:
        data = tif.read(1, masked=True, fill_value=-9999) / 10_000

    # Clamp surface reflectance values to the range [0, 1].
    return np.ma.masked_outside(data, 0, 1)


def select_tags(tags: Tags) -> Tags:
    """
    Selects tags from the input tags that are relevant to the HLS VI product.

    Args:
        tags: Mapping of tags from an instrument band image.

    Returns:
        Mapping of relevant VI tags.
    """
    return {
        "ACCODE": tags["ACCODE"],
        "cloud_coverage": tags.get("cloud_coverage"),
        "HORIZONTAL_CS_NAME": tags.get("HORIZONTAL_CS_NAME"),
        "MEAN_SUN_AZIMUTH_ANGLE": tags.get("MEAN_SUN_AZIMUTH_ANGLE"),
        "MEAN_SUN_ZENITH_ANGLE": tags.get("MEAN_SUN_ZENITH_ANGLE"),
        "MEAN_VIEW_AZIMUTH_ANGLE": tags.get("MEAN_VIEW_AZIMUTH_ANGLE"),
        "MEAN_VIEW_ZENITH_ANGLE": tags.get("MEAN_VIEW_ZENITH_ANGLE"),
        "NBAR_SOLAR_ZENITH": tags.get("NBAR_SOLAR_ZENITH"),
        "SPACECRAFT_NAME": tags.get("SPACECRAFT_NAME"),
        "TILE_ID": tags.get("SENTINEL2_TILEID"),
        "SENSING_TIME": tags.get("SENSING_TIME"),
        "SENSOR": tags.get("SENSOR"),
        "spatial_coverage": tags.get("spatial_coverage"),
    }


def write_granule_indices(output_dir: Path, granule: Granule):
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
):
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
        nodata=data.fill_value,
    ) as dst:
        dst.write(data.filled(), 1)
        dst.update_tags(
            **granule.tags,
            longname=index.value,
            HLS_VI_PROCESSING_TIME=processing_time,
        )

    # Create browse image using NDVI
    if index == Index.NDVI:
        plt.imsave(str(output_path.with_suffix(".jpeg")), data, dpi=300, cmap="gray")


def evi(data: BandData) -> np.ma.masked_array:
    b, r, nir = data[Band.B], data[Band.R], data[Band.NIR]
    return 10_000 * 2.5 * (nir - r) / (nir + 6 * r - 7.5 * b + 1)  # type: ignore


def msavi(data: BandData) -> np.ma.masked_array:
    r, nir = data[Band.R], data[Band.NIR]
    sqrt_term = (2 * nir + 1) ** 2 - 8 * (nir - r)  # type: ignore

    result: np.ma.masked_array = 10_000 * np.ma.where(
        sqrt_term >= 0,
        (2 * nir + 1 - np.sqrt(sqrt_term)) / 2,  # type: ignore
        np.nan,
    )
    result.fill_value = r.fill_value

    return result


def nbr(data: BandData) -> np.ma.masked_array:
    nir, swir2 = data[Band.NIR], data[Band.SWIR2]
    return 10_000 * (nir - swir2) / (nir + swir2)  # type: ignore


def nbr2(data: BandData) -> np.ma.masked_array:
    swir1, swir2 = data[Band.SWIR1], data[Band.SWIR2]
    return 10_000 * (swir1 - swir2) / (swir1 + swir2)  # type: ignore


def ndmi(data: BandData) -> np.ma.masked_array:
    nir, swir1 = data[Band.NIR], data[Band.SWIR1]
    return 10_000 * (nir - swir1) / (nir + swir1)  # type: ignore


def ndvi(data: BandData) -> np.ma.masked_array:
    r, nir = data[Band.R], data[Band.NIR]
    return 10_000 * (nir - r) / (nir + r)  # type: ignore


def ndwi(data: BandData) -> np.ma.masked_array:
    g, nir = data[Band.G], data[Band.NIR]
    return 10_000 * (g - nir) / (g + nir)  # type: ignore


def savi(data: BandData) -> np.ma.masked_array:
    r, nir = data[Band.R], data[Band.NIR]
    return 10_000 * 1.5 * (nir - r) / (nir + r + 0.5)  # type: ignore


def tvi(data: BandData) -> np.ma.masked_array:
    g, r, nir = data[Band.G], data[Band.R], data[Band.NIR]
    # We do NOT multiply by 10_000 like we do for other indices.
    return (120 * (nir - g) - 200 * (r - g)) / 2  # type: ignore


class Index(Enum):
    EVI = "Enhanced Vegetation Index"
    MSAVI = "Modified Soil-Adjusted Vegetation Index"
    NBR = "Normalized Burn Ratio"
    NBR2 = "Normalized Burn Ratio 2"
    NDMI = "Normalized Difference Moisture Index"
    NDVI = "Normalized Difference Vegetation Index"
    NDWI = "Normalized Difference Water Index"
    SAVI = "Soil-Adjusted Vegetation Index"
    TVI = "Triangular Vegetation Index"

    def __init__(self, longname: str) -> None:
        function_name = self.name.lower()
        index_function: Optional[IndexFunction] = globals().get(function_name)

        if not index_function or not callable(index_function):
            raise ValueError(f"Index function not found: {function_name}")

        self.longname = longname
        self.compute_index = index_function

    def __call__(self, data: BandData) -> np.ma.masked_array:
        return np.ma.round(self.compute_index(data)).astype(np.int16)


def parse_args() -> Tuple[Path, Path]:
    short_options = "i:o:"
    long_options = ["inputdir=", "outputdir="]
    command = os.path.basename(sys.argv[0])
    help_text = f"usage: {command} -i <input_dir> -o <output_dir>"

    argv = sys.argv[1:]

    try:
        options, _ = getopt.getopt(argv, short_options, long_options)
    except getopt.GetoptError:
        print(help_text, file=sys.stderr)
        sys.exit(2)

    input_dir, output_dir = None, None

    for option, value in options:
        if option in ("-i", "--inputdir"):
            input_dir = value
        elif option in ("-o", "--outputdir"):
            output_dir = value

    if input_dir is None or output_dir is None:
        print(help_text, file=sys.stderr)
        sys.exit(2)

    return Path(input_dir), Path(output_dir)


def main():
    input_dir, output_dir = parse_args()
    write_granule_indices(output_dir, read_granule_bands(input_dir))


if __name__ == "__main__":
    main()
