import click
import datetime
import numpy as np
import rasterio
import time
import os
import tempfile
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt

"""
inputs:
       HLS granule id

outputs:
       Normalized Difference Vegetation Index, Normalized Difference Water Index, Normalized Difference Water Index,
       Normalized Burn Ratio, Normalized Burn Ration 2, Enhanced Vegetation Index, Soil-Adjusted Vegetation Index,
       Modified Soil-Adjusted Vegetation Index, Triangular Vegetation Index 

"""

start_time = time.time()

# input_bucket = "s3://vegetationindice"
input_bucket = "code/data"
# output_dir = "/Users/brad/Downloads/hls/hls_vi_sample/output20"
output_dir = "code/temp"
hls_granule_id = "HLS.L30.T06WVS.2024120T211159.v2.0"
run_id = "brad_test_samples"

"""
inputs:
       HLS granule id

outputs:
       Normalized Difference Vegetation Index, Normalized Difference Water Index, Normalized Difference Water Index,
       Normalized Burn Ratio, Normalized Burn Ration 2, Enhanced Vegetation Index, Soil-Adjusted Vegetation Index,
       Modified Soil-Adjusted Vegetation Index, Triangular Vegetation Index 

"""

start_time = time.time()


# @click.command()
# @click.option(
#     "--input_bucket",
#     default="s3://vegetationindice",
#     help="S3 bucket path",
# )
# @click.option(
#     "--run_id",
#     default="brad_test_samples",
#     help="Run ID",
# )
# @click.option(
#     "--hls_granule_id",
#     default="HLS.L30.T06WVS.2024120T211159.v2.0",
#     help="HLS granule ID",
# )
# @click.option(
#     "--output_dir",
#     default="/Users/brad/Downloads/hls/hls_vi_sample/output20",
#     help="Output bucket",
# )


def generate_vi_metadata(vi_granule_file, size_of_vi_files, HLS_metadata_file):
    """
    Function allows us to create the metadata file for the VI granules

    Args:
        file1: HLS-VI granule
        file2: XML metadata file for the original HLS granule.
    """
    dataset = rasterio.open(vi_granule_file)
    hls_metadata = HLS_metadata_file
    dataset_tags = dataset.tags()
    ## extract metadata atribute
    sensing_time = dataset_tags["HLS-VI_PROCESSING_TIME"].split(";")
    # sensing_time = dataset_tags["SENSING_TIME"].split(";")

    source_tree = ET.parse(hls_metadata)

    # update this to copy
    dest_tree = source_tree

    # source_root = source_tree.getroot()
    dest_root = dest_tree.getroot()

    ## GranuleUR
    dest_tree.find("GranuleUR").text = dest_tree.find("GranuleUR").text.replace(
        "HLS", "HLS-VI"
    )

    ## Temporal Values
    time_format = "%Y-%m-%dT%H:%M:%S.%fZ"
    dest_tree.find("InsertTime").text = datetime.datetime.utcnow().strftime(time_format)

    # This needs to be updated to last update time of file
    dest_tree.find("LastUpdate").text = datetime.datetime.utcnow().strftime(time_format)

    ## Collection
    collection = dest_root.find("Collection")
    collection.find("DataSetId").text = "Update HLS-VI New Collection ID String"

    ## DataGranule
    version_id = dest_tree.find("GranuleUR").text[-3:]
    data_granule = dest_root.find("DataGranule")
    data_granule.find("DataGranuleSizeInBytes").text = str(size_of_vi_files)
    data_granule.find("ProducerGranuleId").text = dest_tree.find("GranuleUR").text[:-5]
    data_granule.find("ProductionDateTime").text = "UPDATE HLS Prodution DATETIME"
    data_granule.find("LocalVersionId").text = version_id

    ## Temporal
    temporal = dest_root.find("Temporal")
    sensing_time1 = sensing_time[0].split("+")[0].replace(" ", "")[:-2]
    sensing_time2 = sensing_time[-1].split("+")[-1].replace(" ", "")[:-2]

    time1 = datetime.datetime.strptime(sensing_time1, time_format[:-1])
    time2 = datetime.datetime.strptime(sensing_time2, time_format[:-1])
    start_time = time1 if time1 < time2 else time2
    end_time = time2 if time1 < time2 else time1
    start_time = time1 if time1 < time2 else time2
    end_time = time2 if time1 < time2 else time1

    temporal.find("RangeDateTime").find("BeginningDateTime").text = start_time.strftime(
        time_format
    )
    temporal.find("RangeDateTime").find("EndingDateTime").text = end_time.strftime(
        time_format
    )

    ## write the HLS-Vi metadata
    dest_tree.write(
        hls_metadata.replace("HLS", "HLS-VI"), encoding="utf-8", xml_declaration=True
    )


def input_func(input_bucket, run_id, hls_granule_id, output_dir):
    global sr_key, sat_id, output_bucket
    # sr_key = f"{input_bucket}/{run_id}/{hls_granule_id}"
    sr_key = f"{input_bucket}/{hls_granule_id}"
    sat_id = hls_granule_id.split(".")[1]
    output_bucket = output_dir


input_func(input_bucket, run_id, hls_granule_id, output_dir)

# Returns a dictionary mapping satellite band names to common names


def get_common_band_names(sat_id):
    sr_bands_l30 = ["B02", "B03", "B04", "B05", "B06", "B07"]
    sr_bands_s30 = ["B02", "B03", "B04", "B8A", "B11", "B12"]
    common_bands = ["B", "G", "R", "NIR", "SWIR1", "SWIR2"]

    bands_mapping = {
        "L30": dict(zip(sr_bands_l30, common_bands)),
        "S30": dict(zip(sr_bands_s30, common_bands)),
    }
    return bands_mapping[sat_id]


# Call the function and receive the returned dictionary
sr_bands_common = get_common_band_names(sat_id)
(
    print(sr_bands_common)
    if sr_bands_common is not None
    else print("Incorrect satellite id")
)


# Function to open file, read data, and extract metadata
def open_file_and_extract_metadata(base, band, band_name):
    print(f"Reading {base}.{band}.tif")
    with rasterio.open(f"{base}.{band}.tif") as src:
        data = src.read(1, masked=True) * 0.0001  # Read the data with masking
        data.name = band_name
        if src.nodata is not None:
            data = np.ma.masked_equal(data, src.nodata)  # Mask the NoData values

        data = np.ma.masked_less(data, 0)

        # Extract metadata attributes
        metadata = {
            "ACCODE": src.tags()["ACCODE"],
            "cloud_coverage": src.tags().get("cloud_coverage", None),
            "HORIZONTAL_CS_NAME": src.tags().get("HORIZONTAL_CS_NAME", None),
            "MEAN_SUN_AZIMUTH_ANGLE": src.tags().get("MEAN_SUN_AZIMUTH_ANGLE", None),
            "MEAN_SUN_ZENITH_ANGLE": src.tags().get("MEAN_SUN_ZENITH_ANGLE", None),
            "MEAN_VIEW_AZIMUTH_ANGLE": src.tags().get("MEAN_VIEW_AZIMUTH_ANGLE", None),
            "MEAN_VIEW_ZENITH_ANGLE": src.tags().get("MEAN_VIEW_ZENITH_ANGLE", None),
            "NBAR_SOLAR_ZENITH": src.tags().get("NBAR_SOLAR_ZENITH", None),
            "SPACECRAFT_NAME": src.tags().get("SPACECRAFT_NAME", None),
            "TILE_ID": src.tags().get("SENTINEL2_TILEID", None),
            "SENSING_TIME": src.tags().get("SENSING_TIME", None),
            "SENSOR": src.tags().get("SENSOR", None),
            "spatial_coverage": src.tags().get("spatial_coverage", None),
        }

    return data, metadata


# Open dataset for each band and extract metadata
if sr_bands_common is not None:
    common_bands = list(sr_bands_common.values())
    sr_data = {}
    metadata_list = []
    crs = None
    transform = None
    for band, band_name in sr_bands_common.items():
        data, metadata = open_file_and_extract_metadata(sr_key, band, band_name)
        sr_data[band_name] = data
        metadata_list.append(metadata)

    with rasterio.open(f"{sr_key}.{band}.tif") as src:
        crs = src.crs
        transform = src.transform

    # Convert the list of metadata dictionaries to a single dictionary
    extracted_attributes = {k: v for d in metadata_list for k, v in d.items()}

    # Stack the data arrays into an array
    # sr_ds = np.stack(sr_data, axis=-1)
    sr_ds = sr_data
    # print("Dataset shape:", sr_ds.shape)

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

    # Creat browse image using NDVI
    if "NDVI" in output_path:
        browse = output_path.replace(".tif", ".png")
        plt.imsave(browse, raster_data, dpi=300, cmap="gray")


def generate_vi_rasters(
    sr_ds,
    hls_granule_id,
    sat_id,
    **extracted_attributes,
):
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

    # Define variables for bands based on common name
    red = sr_ds["R"]
    blue = sr_ds["B"]
    green = sr_ds["G"]
    nir = sr_ds["NIR"]
    swir1 = sr_ds["SWIR1"]
    swir2 = sr_ds["SWIR2"]

    # Calculate spectral indices
    NDVI_ = (nir - red) / (nir + red)
    NDWI_ = (green - nir) / (green + nir)
    NDMI_ = (nir - swir1) / (nir + swir1)
    NBR_ = (nir - swir2) / (nir + swir2)
    NBR2_ = (swir1 - swir2) / (swir1 + swir2)
    EVI_ = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)
    SAVI_ = 1.5 * (nir - red) / (nir + red + 0.5)
    MSAVI_ = np.where(
        (2 * nir + 1) ** 2 - 8 * (nir - red) >= 0,
        (2 * nir + 1 - np.sqrt((2 * nir + 1) ** 2 - 8 * (nir - red))) / 2,
        np.nan,
    )
    # MSAVI_ = (2 * nir + 1 - np.sqrt((2 * nir + 1) ** 2 - 8 * (nir - red))) / 2
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
        "HORIZONTAL_CS_NAME": extracted_attributes.get("HORIZONTAL_CS_NAME", None),
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
        "TILE_ID": extracted_attributes.get("TILE_ID", None),
        "SENSOR": extracted_attributes.get("SENSOR", None),
        "SENSING_TIME": extracted_attributes.get("SENSING_TIME", None),
        "spatial_coverage": extracted_attributes.get("spatial_coverage", None),
        "HLS-VI_PROCESSING_TIME": datetime.datetime.now().strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
    }

    # Save rasters
    file_size = 0
    for index_name, index_data in zip(
        ["NDVI", "NDWI", "NDMI", "NBR", "NBR2", "EVI", "SAVI", "MSAVI", "TVI"],
        [NDVI_, NDWI_, NDMI_, NBR_, NBR2_, EVI_, SAVI_, MSAVI_, TVI_],
    ):
        index_longname = longname.get(index_name, "")
        if index_longname:
            attributes["longname"] = index_longname

        # Determine the output path for the current index
        fname = f"HLS_VI.{sat_id}.{tile_id}.{acq_date}.v2.0"
        index_output_path = os.path.join(output_bucket, f"{fname}.{index_name}.tif")

        # Scale and convert the data to int16 if the index is not "TVI"
        if index_name != "TVI":
            scale_factor = 10000
            scaled_data = np.round(index_data * scale_factor).astype(np.int16)
        else:
            scaled_data = index_data.astype(np.int16)
        # with tempfile.NamedTemporaryFile() as tmp:
        #     scaled_data.rasterio(
        #         tmp.name, driver="COG", tags=attributes, compress="deflate"
        #     )

        # Save the raster using the save_raster function
        save_raster(
            raster_data=scaled_data,
            output_path=index_output_path,
            transform=transform,
            crs=crs,
            tags=attributes,
            compress="deflate",
        )
        file_size += os.stat(index_output_path).st_size

    return index_output_path, file_size


vi_granule_path, size_of_file = generate_vi_rasters(
    sr_ds,
    hls_granule_id,
    sat_id,
    **extracted_attributes,
)
generate_vi_metadata(
    vi_granule_path,
    size_of_file,
    "code/data/HLS.L30.T06WVS.2024120T211159.v2.0.cmr.xml",
)

end_time = time.time()
runtime = end_time - start_time
print("Total runtime:", runtime, "seconds")
