import rasterio
import numpy as np
import datetime
from rasterio.transform import from_origin
import os
from rasterio.crs import CRS

"""
inputs:
       HLS granule id

outputs:
       Normalized Difference Vegetation Index, Normalized Difference Water Index, Normalized Difference Water Index,
       Normalized Burn Ratio, Normalized Burn Ration 2, Enhanced Vegetation Index, Soil-Adjusted Vegetation Index,
       Modified Soil-Adjusted Vegetation Index, Triangular Vegetation Index 

"""

# Construct S3 key for accessing data within S3 bucket
bucket = "s3://hls-debug-output"
run_id = "brad_test_samples"
hls_granule_id = "HLS.L30.T22JBQ.2024055T133022.v2.0"
sr_key = f"{bucket}/{run_id}/{hls_granule_id}/{hls_granule_id}"
sat_id = hls_granule_id.split(".")[1]

print(sr_key)


# Returns a dictionary mapping satellite band names to common names.
def get_common_band_names(sat_id):
    sr_bands_l30 = ["B02", "B03", "B04", "B05", "B06", "B07"]
    sr_bands_s30 = ["B02", "B03", "B04", "B8A", "B11", "B12"]
    common_bands = ["B", "G", "R", "NIR", "SWIR1", "SWIR2"]

    bands_mapping = {
        "L30": dict(zip(sr_bands_l30, common_bands)),
        "S30": dict(zip(sr_bands_s30, common_bands)),
    }

    if sat_id not in bands_mapping:
        raise ValueError("Incorrect satellite id")

    return bands_mapping[sat_id]


# Call the function and receive the returned dictionary
sr_bands_common = get_common_band_names(sat_id)
(
    print(sr_bands_common)
    if sr_bands_common is not None
    else print("Incorrect satellite id")
)


def open_file(base, band, band_name):
    print(f"Reading {base}.{band}.tif")
    with rasterio.open(f"{base}.{band}.tif") as src:
        data = src.read(1, masked=True)  # Read the data with masking
        if src.nodata is not None:
            data = np.ma.masked_equal(data, src.nodata)  # Mask the NoData values
        scale_factor = (
            src.scale[0] if hasattr(src, "scale") else 1.0
        )  # Get the scale factor
        offset = src.offset[0] if hasattr(src, "offset") else 0.0  # Get the offset
        data = data * scale_factor + offset  # Apply scaling and offset
        metadata = {
            "width": src.width,
            "height": src.height,
            "crs": src.crs,
            "transform": src.transform,
            "ACCODE": src.tags().get("ACCODE", None),
            "cloud_coverage": src.tags().get("cloud_coverage", None),
            "HORIZONTAL_CS_CODE": src.tags().get("HORIZONTAL_CS_CODE", None),
            "MEAN_SUN_AZIMUTH_ANGLE": src.tags().get("MEAN_SUN_AZIMUTH_ANGLE", None),
            "MEAN_SUN_ZENITH_ANGLE": src.tags().get("MEAN_SUN_ZENITH_ANGLE", None),
            "MEAN_VIEW_AZIMUTH_ANGLE": src.tags().get("MEAN_VIEW_AZIMUTH_ANGLE", None),
            "MEAN_VIEW_ZENITH_ANGLE": src.tags().get("MEAN_VIEW_ZENITH_ANGLE", None),
            "NBAR_SOLAR_ZENITH": src.tags().get("NBAR_SOLAR_ZENITH", None),
            "SPACECRAFT_NAME": src.tags().get("SPACECRAFT_NAME", None),
            "TILE_ID": src.tags().get("TILE_ID", None),
            "spatial_coverage": src.tags().get("spatial_coverage", None),
            # Add more metadata fields as needed
        }
    return data, metadata


# Function to open file, read data, and extract metadata
def open_file_and_extract_metadata(base, band, band_name):
    print(f"Reading {base}.{band}.tif")
    with rasterio.open(f"{base}.{band}.tif") as src:
        data = src.read(1, masked=True)  # Read the data with masking
        if src.nodata is not None:
            data = np.ma.masked_equal(data, src.nodata)  # Mask the NoData values
        scale_factor = (
            src.scale[0] if hasattr(src, "scale") else 1.0
        )  # Get the scale factor
        offset = src.offset[0] if hasattr(src, "offset") else 0.0  # Get the offset
        data = data * scale_factor + offset  # Apply scaling and offset
        # Extract metadata attributes
        metadata = {
            "ACCODE": src.tags()["ACCODE"],
            "cloud_coverage": src.tags().get("cloud_coverage", None),
            "HORIZONTAL_CS_CODE": src.tags().get("HORIZONTAL_CS_CODE", None),
            "MEAN_SUN_AZIMUTH_ANGLE": src.tags().get("MEAN_SUN_AZIMUTH_ANGLE", None),
            "MEAN_SUN_ZENITH_ANGLE": src.tags().get("MEAN_SUN_ZENITH_ANGLE", None),
            "MEAN_VIEW_AZIMUTH_ANGLE": src.tags().get("MEAN_VIEW_AZIMUTH_ANGLE", None),
            "MEAN_VIEW_ZENITH_ANGLE": src.tags().get("MEAN_VIEW_ZENITH_ANGLE", None),
            "NBAR_SOLAR_ZENITH": src.tags().get("NBAR_SOLAR_ZENITH", None),
            "SPACECRAFT_NAME": src.tags().get("SPACECRAFT_NAME", None),
            "TILE_ID": src.tags().get("TILE_ID", None),
            "spatial_coverage": src.tags().get("spatial_coverage", None),
        }
    return data, metadata


# Open dataset for each band and extract metadata
if sr_bands_common is not None:
    common_bands = list(sr_bands_common.values())
    sr_data = []
    metadata_list = []
    for band, band_name in sr_bands_common.items():
        data, metadata = open_file_and_extract_metadata(sr_key, band, band_name)
        sr_data.append(data)
        metadata_list.append(metadata)

    # Convert the list of metadata dictionaries to a single dictionary
    extracted_attributes = {k: v for d in metadata_list for k, v in d.items()}

    # Stack the data arrays into an array
    sr_ds = np.stack(sr_data, axis=-1)
    print("Dataset shape:", sr_ds.shape)

    # Check if the extraction was successful and print the extracted attributes
    if extracted_attributes:
        print("Extracted attributes:")
        for key, value in extracted_attributes.items():
            print(f"{key}: {value}")
else:
    print("Unable to open dataset")


# Define the save_raster function here
def save_raster(
    raster_data,
    output_path,
    transform,
    crs,
    driver="GTiff",
    compress="deflate",
    tags=None,
):
    """
    Save raster data to a GeoTIFF file using rasterio.

    Args:
    - raster_data: NumPy array containing raster data.
    - output_path: Output file path for the GeoTIFF file.
    - transform: Affine transform object defining the transformation.
    - crs: Coordinate reference system for the raster.
    - driver: Output raster driver (default is GTiff).
    - compress: Compression method (default is deflate).
    - tags: Optional dictionary of tags to include in the GeoTIFF file.

    Returns:
    - None
    """
    with rasterio.open(
        output_path,
        "w",
        driver=driver,
        width=raster_data.shape[1],
        height=raster_data.shape[0],
        count=1,
        dtype=raster_data.dtype,
        crs=crs,
        transform=transform,
        compress=compress,
    ) as dst:
        dst.write(raster_data, 1)
        if tags:
            dst.update_tags(**tags)


def generate_vi_rasters(sr_ds, hls_granule_id, **extracted_attributes):
    """
    Calculate and save VI rasters as separate COGs for the following spectral indices:
    "NDVI", "NDWI", "NDMI", "NBR", "NBR2","EVI", "SAVI", "MSAVI", "TVI"

    params
    :sr_ds: surface reflectance dataset containing R, B, G, NIR, SWIR1, SWIR2 bands as data variables
    :granule_id: HLS base granule id name
    :returns:
    """
    sat_id = hls_granule_id.split(".")[1]
    tile_id = hls_granule_id.split(".")[2]
    acq_date = hls_granule_id.split(".")[3]

    # HLS-VI base name
    fname = f"HLS_VI.{sat_id}.{tile_id}.{acq_date}.v2.0"
    output_dir = "./output/"
    os.makedirs(output_dir, exist_ok=True)

    # Define variables for bands based on common name
    red = sr_ds[..., 0]
    blue = sr_ds[..., 1]
    green = sr_ds[..., 2]
    nir = sr_ds[..., 3]
    swir1 = sr_ds[..., 4]
    swir2 = sr_ds[..., 5]

    # Calculate spectral indices
    NDVI_ = (nir - red) / (nir + red)
    NDWI_ = (green - nir) / (green + nir)
    NDMI_ = (nir - swir1) / (nir + swir1)
    NBR_ = (nir - swir2) / (nir + swir2)
    NBR2_ = (swir1 - swir2) / (swir1 + swir2)
    EVI_ = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)
    SAVI_ = 1.5 * (nir - red) / (nir + red + 0.5)
    MSAVI_ = (2 * nir + 1 - np.sqrt((2 * nir + 1) ** 2 - 8 * (nir - red))) / 2
    TVI_ = (120 * (nir - green) - 200 * (red - green)) / 2

    # Define the dictionary of long names for each index
    longname = {
        "NDVI": "Normalized Difference Vegetation Index",
        "NDWI": "Normalized Difference Water Index",
        "NDMI": "Normalized Difference Moisture Index",
        "NBR": "Normalized Burn Ratio",
        "NBR2": "Normalized Burn Ratio 2",
        "EVI": "Enhanced Vegetation Index",
        "SAVI": "Soil-Adjusted Vegetation Index",
        "MSAVI": "Modified Soil-Adjusted Vegetation Index",
        "TVI": "Triangular Vegetation Index",
    }

    # Concatenate all long names into one string
    longname_str = ", ".join([f"{index}: {name}" for index, name in longname.items()])

    # Define metadata attributes
    attributes = {
        "longname": longname_str,
        "ACCODE": extracted_attributes.get("ACCODE", ""),
        "cloud_coverage": extracted_attributes.get("cloud_coverage", None),
        "HORIZONTAL_CS_CODE": extracted_attributes.get("HORIZONTAL_CS_CODE", None),
        "MEAN_SUN_AZIMUTH_ANGLE": extracted_attributes.get(
            "MEAN_SUN_AZIMUTH_ANGLE", None
        ),
        "MEAN_SUN_ZENITH_ANGLE": extracted_attributes.get(
            "MEAN_SUN_ZENITH_ANGLE", None
        ),
        "MEAN_VIEW_AZIMUTH_ANGLE": extracted_attributes.get(
            "MEAN_VIEW_AZIMUTH_ANGLE", None
        ),
        "MEAN_VIEW_ZENITH_ANGLE": extracted_attributes.get(
            "MEAN_VIEW_ZENITH_ANGLE", None
        ),
        "NBAR_SOLAR_ZENITH": extracted_attributes.get("NBAR_SOLAR_ZENITH", None),
        "SPACECRAFT_NAME": extracted_attributes.get("SPACECRAFT_NAME", None),
        "TILE_ID": extracted_attributes.get("TILE_ID", None),
        "spatial_coverage": extracted_attributes.get("spatial_coverage", None),
        "HLS_PROCESSING_TIME": datetime.datetime.now().strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
    }

    # Save rasters
    for index_name, index_data in zip(
        ["NDVI", "NDWI", "NDMI", "NBR", "NBR2", "EVI", "SAVI", "MSAVI", "TVI"],
        [NDVI_, NDWI_, NDMI_, NBR_, NBR2_, EVI_, SAVI_, MSAVI_, TVI_],
    ):
        index_longname = longname.get(index_name, "")
        if index_longname:
            attributes["longname"] = index_longname

        # Determine the output path for the current index
        index_output_path = output_dir + f"{fname}.{index_name}.tif"

        # Save the raster using the save_raster function
        save_raster(
            raster_data=index_data,
            output_path=index_output_path,
            transform=None,  # You need to define the correct transform here
            crs=None,  # You need to define the correct CRS here
            tags=attributes,
        )

    generate_vi_rasters(sr_ds, hls_granule_id, **extracted_attributes)
