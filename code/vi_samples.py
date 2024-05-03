import rasterio
import rioxarray as rxr
import xarray as xr
import numpy as np
import datetime
import tempfile
import xml.etree.ElementTree as ET

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
hls_granule_id = "HLS.L30.T06WVS.2024120T211159.v2.0"
# sr_key = f"{bucket}/{run_id}/{hls_granule_id}/{hls_granule_id}"
sr_key = f"data/{hls_granule_id}"
sat_id = hls_granule_id.split(".")[1]
print(sr_key)


def generate_vi_metadata(file1, file2, metadata_name):
    """
    Function allows us to create the metadata file for the VI granules

    Args:
        file1: HLS-VI granule
        file2: XML metadata file for the original HLS granule.
    """
    dataset = rasterio.open(file1)
    hls_metadata = file2
    dataset_tags = dataset.tags()
    ## extract metadata atribute
    sensing_time = dataset_tags["HLS_PROCESSING_TIME"].split(";")

    source_tree = ET.parse(hls_metadata)

    # update this to copy
    dest_tree = source_tree

    source_root = source_tree.getroot()
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
    collection.find("DataSetId").text = metadata_name.replace("HLS", "HLS_VI")

    ## DataGranule
    version_id = dest_tree.find("GranuleUR").text[-3:]
    data_granule = dest_root.find("DataGranule")
    data_granule.find("DataGranuleSizeInBytes").text = "XYZ"
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
        metadata_name.replace("HLS", "HLS_VI") + "_metadata.xml",
        encoding="utf-8",
        xml_declaration=True,
    )


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


# Open raster file and apply scaling and masking
def open_file(base, band, band_name):
    print(f"Reading {base}.{band}.tif")
    da = rxr.open_rasterio(f"{base}.{band}.tif", mask_and_scale=True)
    da.name = band_name
    return da


# Open dataset for each band
if sr_bands_common is not None:
    common_bands = list(sr_bands_common.values())
    sr_das = [
        open_file(sr_key, band, band_name)
        for band, band_name in sr_bands_common.items()
    ]
    # Merge the bands into an xarray dataset
    sr_ds = xr.merge(sr_das, combine_attrs="drop_conflicts")
    # print(sr_ds)
else:
    print("Unable to open dataset")


# Extract specific attributes from the dataset
def extract_specific_attributes(sr_ds):
    attributes = {}
    attrs_to_extract = [
        "ACCODE",
        "cloud_coverage",
        "HORIZONTAL_CS_CODE",
        "MEAN_SUN_AZIMUTH_ANGLE",
        "MEAN_SUN_ZENITH_ANGLE",
        "MEAN_VIEW_AZIMUTH_ANGLE",
        "MEAN_VIEW_ZENITH_ANGLE",
        "NBAR_SOLAR_ZENITH",
        "SPACECRAFT_NAME",
        "TILE_ID",
        "spatial_coverage",
    ]

    for attr in attrs_to_extract:
        if attr in sr_ds.attrs:
            attributes[attr] = sr_ds.attrs[attr]

    return attributes


extracted_attributes = extract_specific_attributes(sr_ds)

# Check if the extraction was successful and print the extracted attributes
if extracted_attributes:
    print("Extracted attributes:")
    for key, value in extracted_attributes.items():
        print(f"{key}: {value}")


def generate_vi_rasters(
    sr_ds,
    hls_granule_id,
    ACCODE,
    cloud_coverage,
    HORIZONTAL_CS_CODE,
    MEAN_SUN_AZIMUTH_ANGLE,
    MEAN_SUN_ZENITH_ANGLE,
    MEAN_VIEW_AZIMUTH_ANGLE,
    MEAN_VIEW_ZENITH_ANGLE,
    NBAR_SOLAR_ZENITH,
    SPACECRAFT_NAME,
    TILE_ID,
    spatial_coverage,
    xml_metadata_file,
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

    ## HLS-VI base name - NOTE: Just saving locally now; will need to update to staging bucket on MCP
    fname = f"HLS_VI.{sat_id}.{tile_id}.{acq_date}.v2.0"
    path = "./"

    # Define variables for bands based on common name
    red = sr_ds["R"]
    blue = sr_ds["B"]
    green = sr_ds["G"]
    nir = sr_ds["NIR"]
    swir1 = sr_ds["SWIR1"]
    swir2 = sr_ds["SWIR2"]

    # The following spectral indices are common for both L30 and S30
    NDVI_ = (nir - red) / (nir + red)
    NDWI_ = (green - nir) / (green + nir)
    NDMI_ = (nir - swir1) / (nir + swir1)
    NBR_ = (nir - swir2) / (nir + swir2)
    NBR2_ = (swir1 - swir2) / (swir1 + swir2)
    EVI_ = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)
    SAVI_ = 1.5 * (nir - red) / (nir + red + 0.5)
    MSAVI_ = (
        2 * nir + 1 - np.sqrt((2 * nir + 1) ** 2 - 8 * (nir - red))
    ) / 2  ## Need to look into this because sqrt triggers a warning. May need to replace negative values as nan.
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
        "ACCODE": "LaSRC 3.0.5",
        "cloud_coverage": cloud_coverage,
        "HORIZONTAL_CS_CODE": HORIZONTAL_CS_CODE,
        "MEAN_SUN_AZIMUTH_ANGLE": MEAN_SUN_AZIMUTH_ANGLE,
        "MEAN_SUN_ZENITH_ANGLE": MEAN_SUN_ZENITH_ANGLE,
        "MEAN_VIEW_AZIMUTH_ANGLE": MEAN_VIEW_AZIMUTH_ANGLE,
        "MEAN_VIEW_ZENITH_ANGLE": MEAN_VIEW_ZENITH_ANGLE,
        "NBAR_SOLAR_ZENITH": NBAR_SOLAR_ZENITH,
        "SPACECRAFT_NAME": SPACECRAFT_NAME,
        "TILE_ID": TILE_ID,
        "spatial_coverage": spatial_coverage,
        "HLS_PROCESSING_TIME": datetime.datetime.now().strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
    }

    ## Save rasters
    for index_name, index_data in zip(
        ["NDVI", "NDWI", "NDMI", "NBR", "NBR2", "EVI", "SAVI", "MSAVI", "TVI"],
        [NDVI_, NDWI_, NDMI_, NBR_, NBR2_, EVI_, SAVI_, MSAVI_, TVI_],
    ):
        index_longname = longname.get(index_name, "")
        metadata_name = hls_granule_id + f"_{index_name}"
        if index_longname:
            attributes["longname"] = index_longname
        if index_name == "TVI":
            index_raster = index_data.astype(np.int16)
        else:
            index_raster = (index_data * 1000).astype(np.int16)
        with tempfile.NamedTemporaryFile() as tmp:
            index_raster.rio.to_raster(
                tmp.name, driver="COG", tags=attributes, compress="deflate"
            )
            generate_vi_metadata(tmp.name, xml_metadata_file, metadata_name)
        index_raster.rio.to_raster(
            path + fname + f".{index_name}.tif",
            driver="COG",
            tags=attributes,
            compress="deflate",
        )


generate_vi_rasters(
    sr_ds,
    hls_granule_id,
    extracted_attributes.get("ACCODE", ""),
    extracted_attributes.get("cloud_coverage", None),
    extracted_attributes.get("HORIZONTAL_CS_CODE", None),
    extracted_attributes.get("MEAN_SUN_AZIMUTH_ANGLE", None),
    extracted_attributes.get("MEAN_SUN_ZENITH_ANGLE", None),
    extracted_attributes.get("MEAN_VIEW_AZIMUTH_ANGLE", None),
    extracted_attributes.get("MEAN_VIEW_ZENITH_ANGLE", None),
    extracted_attributes.get("NBAR_SOLAR_ZENITH", None),
    extracted_attributes.get("SPACECRAFT_NAME", None),
    extracted_attributes.get("TILE_ID", None),
    extracted_attributes.get("spatial_coverage", None),
    xml_metadata_file="data/G2963019115-LPCLOUD.xml",
)
