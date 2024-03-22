import rasterio
import rioxarray as rxr
import xarray as xr

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

    import numpy as np

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

    import datetime

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
        if index_longname:
            attributes["longname"] = index_longname
        if index_name == "TVI":
            index_raster = index_data.astype(np.int16)
        else:
            index_raster = (index_data * 1000).astype(np.int16)
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
)
