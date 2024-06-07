import getopt
import os
import re
import sys
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Optional, Tuple
from typing_extensions import TypeAlias

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import rasterio.crs
import rasterio.transform

"""
inputs:
       HLS granule id

outputs:
       Normalized Difference Vegetation Index, Normalized Difference Water Index,
       Normalized Difference Water Index, Normalized Burn Ratio,
       Normalized Burn Ration 2, Enhanced Vegetation Index,
       Soil-Adjusted Vegetation Index, Modified Soil-Adjusted Vegetation Index,
       Triangular Vegetation Index
"""

Tags: TypeAlias = Mapping[str, Optional[str]]


class HarmonizedBand(Enum):
    B = "B"
    G = "G"
    R = "R"
    NIR = "NIR"
    SWIR1 = "SWIR1"
    SWIR2 = "SWIR2"

    @classmethod
    def from_instrument_band(cls, instrument_band: str) -> "HarmonizedBand":
        return {
            "B02": cls.B,
            "B03": cls.G,
            "B04": cls.R,
            "B05": cls.NIR,
            "B06": cls.SWIR1,
            "B07": cls.SWIR2,
            "B8A": cls.NIR,
            "B11": cls.SWIR1,
            "B12": cls.SWIR2,
        }[instrument_band]


class IndexKind(Enum):
    EVI = "Enhanced Vegetation Index"
    MSAVI = "Modified Soil-Adjusted Vegetation Index"
    NBR = "Normalized Burn Ratio"
    NBR2 = "Normalized Burn Ratio 2"
    NDMI = "Normalized Difference Moisture Index"
    NDVI = "Normalized Difference Vegetation Index"
    NDWI = "Normalized Difference Water Index"
    SAVI = "Soil-Adjusted Vegetation Index"
    TVI = "Triangular Vegetation Index"


def generate_indexes(*, input_dir: str, output_dir: str):
    granule_id = os.path.basename(input_dir)
    crs, transform, tags, bands_data = read_bands(input_dir)
    indexes = compute_indexes(
        **{band.name.lower(): data for band, data in bands_data.items()}
    )
    write_indexes(output_dir, granule_id, crs, transform, tags, indexes)


def parse_granule_id(granule_id: str) -> Tuple[str, str, str, str]:
    # Assume granule_id is formatted as follows, where {version} may contain dots:
    # HLS.{instrument}.{tile_id}.{acquisition_date}.{version}
    match = re.match(
        r"HLS[.](?P<instrument>[^.]+)[.](?P<tile_id>[^.]+)[.]"
        r"(?P<acquisition_date>[^.]+)[.](?P<version>.+)",
        granule_id,
    )

    if not match:
        raise ValueError(f"Invalid granule ID: {granule_id}")

    return (
        match["instrument"],
        match["tile_id"],
        match["acquisition_date"],
        match["version"],
    )


def read_bands(
    input_dir: str,
) -> Tuple[
    rasterio.crs.CRS,
    rasterio.transform.Affine,
    Tags,
    Mapping[HarmonizedBand, np.ndarray],
]:
    tif_paths = [
        os.path.join(input_dir, filename)
        for filename in os.listdir(input_dir)
        if filename.endswith(".tif")
    ]

    # All bands have the same CRS, transform, and tags, so we can use the first one to
    # get this information.
    with rasterio.open(tif_paths[0]) as tif:
        crs = tif.crs
        transform = tif.transform
        tags = tif.tags()

    return (
        crs,
        transform,
        select_tags(tags),
        dict(map(read_band, tif_paths)),
    )


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


def read_band(tif_path: str) -> Tuple[HarmonizedBand, np.ndarray]:
    *_, band_name, _ext = os.path.basename(tif_path).split(".")
    harmonized_band = HarmonizedBand.from_instrument_band(band_name)

    with rasterio.open(tif_path) as tif:
        data = tif.read(1, masked=True) * 0.0001
        data.name = harmonized_band.name

    return harmonized_band, np.ma.masked_less(data, 0)


def compute_indexes(
    *,
    b: np.ndarray,
    g: np.ndarray,
    r: np.ndarray,
    nir: np.ndarray,
    swir1: np.ndarray,
    swir2: np.ndarray,
) -> Mapping[IndexKind, np.ndarray]:
    indexes_except_tvi: Mapping[IndexKind, np.ndarray] = {
        IndexKind.EVI: 2.5 * (nir - r) / (nir + 6 * r - 7.5 * b + 1),
        IndexKind.MSAVI: np.where(
            (2 * nir + 1) ** 2 - 8 * (nir - r) >= 0,  # type: ignore
            (2 * nir + 1 - np.sqrt((2 * nir + 1) ** 2 - 8 * (nir - r))) / 2,  # type: ignore  # noqa: E501
            np.nan,
        ),
        IndexKind.NBR: (nir - swir2) / (nir + swir2),
        IndexKind.NBR2: (swir1 - swir2) / (swir1 + swir2),
        IndexKind.NDMI: (nir - swir1) / (nir + swir1),
        IndexKind.NDVI: (nir - r) / (nir + r),
        IndexKind.NDWI: (g - nir) / (g + nir),
        IndexKind.SAVI: 1.5 * (nir - r) / (nir + r + 0.5),
    }

    scaled_indexes: Mapping[IndexKind, np.ndarray] = {
        **{kind: np.round(data * 10_000) for kind, data in indexes_except_tvi.items()},
        IndexKind.TVI: ((120 * (nir - g) - 200 * (r - g)) / 2),  # type: ignore
    }

    return {kind: data.astype(np.int16) for kind, data in scaled_indexes.items()}  # type: ignore   # noqa: E501


def write_indexes(
    output_dir: str,
    granule_id: str,
    crs: rasterio.crs.CRS,
    transform: rasterio.transform.Affine,
    tags: Tags,
    indexes: Mapping[IndexKind, np.ndarray],
):
    os.makedirs(output_dir, exist_ok=True)
    processing_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    instrument, tile_id, acquisition_date, version = parse_granule_id(granule_id)

    for kind, data in indexes.items():
        filename = f"HLS-VI.{instrument}.{tile_id}.{acquisition_date}.{version}.{kind.name}.tif"  # noqa: E501
        output_path = os.path.join(output_dir, filename)
        index_tags = {
            **tags,
            "longname": kind.value,
            "HLS-VI_PROCESSING_TIME": processing_time,
        }

        write_index(output_path, crs, transform, index_tags, data)


def write_index(
    output_path: str,
    crs: rasterio.crs.CRS,
    transform: rasterio.transform.Affine,
    tags: Tags,
    data: np.ndarray,
):
    """
    Save raster data to a GeoTIFF file using rasterio.

    Args:
        output_path: Output file path for the GeoTIFF file.
        data: NumPy array containing raster data.
        transform: Affine transform object defining the transformation.
        crs: Coordinate reference system for the raster.
        tags: Mapping of tags to include in the GeoTIFF file.
    """

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        compress="deflate",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(**tags)

    # Creat browse image using NDVI
    if "NDVI" in output_path:
        browse = output_path.replace(".tif", ".png")
        plt.imsave(browse, data, dpi=300, cmap="gray")


def parse_args() -> Tuple[str, str]:
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

    return input_dir, output_dir


def main():
    input_dir, output_dir = parse_args()
    generate_indexes(input_dir=input_dir, output_dir=output_dir)


if __name__ == "__main__":
    main()
