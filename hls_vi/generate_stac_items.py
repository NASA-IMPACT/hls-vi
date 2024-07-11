import datetime
import json
import os

import click
import pystac
import rasterio
import untangle
from geojson import MultiPolygon
from pystac.extensions.eo import Band, EOExtension
from pystac.extensions.projection import ProjectionExtension
from pystac.extensions.scientific import ScientificExtension
from pystac.extensions.view import ViewExtension
from shapely.geometry import shape

# HLS_VI band information
hls_vi_band_info = {
    "NDVI": {
        "band": Band.create(
            name="NDVI",
            common_name="NDVI",
        ),
        "gsd": 30.0,
    },
    "EVI": {
        "band": Band.create(
            name="EVI",
            common_name="EVI",
        ),
        "gsd": 30.0,
    },
    "MSAVI": {
        "band": Band.create(
            name="MSAVI",
            common_name="MSAVI",
        ),
        "gsd": 30.0,
    },
    "NBR": {
        "band": Band.create(
            name="NBR",
            common_name="NBR",
        ),
        "gsd": 30.0,
    },
    "NBR2": {
        "band": Band.create(
            name="NBR2",
            common_name="NBR2",
        ),
        "gsd": 30.0,
    },
    "NDMI": {
        "band": Band.create(
            name="NDMI",
            common_name="NDMI",
        ),
        "gsd": 30.0,
    },
    "NDWI": {
        "band": Band.create(
            name="NDWI",
            common_name="NDWI",
        ),
        "gsd": 30.0,
    },
    "SAVI": {
        "band": Band.create(
            name="SAVI",
            common_name="SAVI",
        ),
        "gsd": 30.0,
    },
    "TVI": {
        "band": Band.create(
            name="TVI",
            common_name="TVI",
        ),
        "gsd": 30.0,
    },
}


def get_geometry(granule):
    multipolygon = []
    for poly in granule.Spatial.HorizontalSpatialDomain.Geometry.GPolygon:
        ring = []
        for point in poly.Boundary.Point:
            geojson_point = [
                float(point.PointLongitude.cdata),
                float(point.PointLatitude.cdata),
            ]
            ring.append(geojson_point)

        closing_point = [
            float(poly.Boundary.Point[0].PointLongitude.cdata),
            float(poly.Boundary.Point[0].PointLatitude.cdata),
        ]
        ring.append(closing_point)
        ringtuple = (ring,)
        multipolygon.append(ringtuple)
    geometry = MultiPolygon(multipolygon)
    return geometry


def process_common_metadata(item, granule):
    start_datetime_str = granule.Temporal.RangeDateTime.BeginningDateTime.cdata
    item_start_datetime = datetime.datetime.strptime(
        start_datetime_str, "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    end_datetime_str = granule.Temporal.RangeDateTime.EndingDateTime.cdata
    item_end_datetime = datetime.datetime.strptime(
        end_datetime_str, "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    item.common_metadata.start_datetime = item_start_datetime
    item.common_metadata.end_datetime = item_end_datetime
    item.common_metadata.platform = granule.Platforms.Platform.ShortName.cdata.lower()
    instrument = (
        granule.Platforms.Platform.Instruments.Instrument.ShortName.cdata.lower()
    )
    if " " in instrument:
        item_instrument = instrument.split()[1]
    else:
        item_instrument = instrument
    item.common_metadata.instruments = [item_instrument]


def process_eo(item, granule):
    eo_extension = EOExtension.ext(item, add_if_missing=True)
    for attribute in granule.AdditionalAttributes.AdditionalAttribute:
        if attribute.Name == "CLOUD_COVERAGE":
            eo_extension.cloud_cover = float(attribute.Values.Value.cdata)


def add_assets(item, granule, endpoint, version):
    item_id = granule.GranuleUR.cdata
    product = item_id.split(".")[1]
    if product == "S30":
        band_info = hls_vi_band_info
        url = f"https://{endpoint}/lp-prod-protected/HLSS30.{version}/{item_id}/"
        public_url = f"https://{endpoint}/lp-prod-public/HLSS30.{version}/{item_id}/"

    if product == "L30":
        band_info = hls_vi_band_info
        url = f"https://{endpoint}/lp-prod-protected/HLSL30.{version}/{item_id}/"
        public_url = f"https://{endpoint}/lp-prod-public/HLSL30.{version}/{item_id}/"

    url_template = url + "{}.{}.tif"

    for band_id, band_info in band_info.items():
        band_url = url_template.format(item_id, band_id)
        asset = pystac.Asset(
            href=band_url, media_type=pystac.MediaType.COG, roles=["data"]
        )
        bands = [band_info["band"]]
        EOExtension.ext(asset).bands = bands
        item.add_asset(band_id, asset)

    thumbnail_url = f"{public_url}{item_id}.jpg"
    thumbnail_asset = pystac.Asset(
        href=thumbnail_url, media_type=pystac.MediaType.JPEG, roles=["thumbnail"]
    )
    item.add_asset("thumbnail", thumbnail_asset)
    item.set_self_href(f"{public_url}{item_id}_stac.json")


def process_projection(item, granule, band1_file):
    proj_ext = ProjectionExtension.ext(item, add_if_missing=True)
    with rasterio.open(band1_file) as band1_dataset:
        proj_ext.transform = band1_dataset.transform
        height, width = band1_dataset.shape
        proj_ext.shape = [height, width]
    for attribute in granule.AdditionalAttributes.AdditionalAttribute:
        if attribute.Name == "MGRS_TILE_ID":
            value = attribute.Values.Value.cdata
            hemi = "326"
            epsg = int(hemi + value[0:2])
            proj_ext.epsg = epsg


def process_view_geometry(item, granule):
    view_extension = ViewExtension.ext(item, add_if_missing=True)
    for attribute in granule.AdditionalAttributes.AdditionalAttribute:
        if attribute.Name == "MEAN_SUN_AZIMUTH_ANGLE":
            view_extension.sun_azimuth = float(attribute.Values.Value.cdata)
        if attribute.Name == "MEAN_VIEW_AZIMUTH_ANGLE":
            view_extension.azimuth = float(attribute.Values.Value.cdata)


def process_scientific(item, granule):
    scientific_extension = ScientificExtension.ext(item, add_if_missing=True)
    for attribute in granule.AdditionalAttributes.AdditionalAttribute:
        if attribute.Name == "IDENTIFIER_PRODUCT_DOI":
            scientific_extension.doi = attribute.Values.Value.cdata


def cmr_to_item(hls_vi_metadata, endpoint, version):
    # band1_file = f"{os.path.splitext(os.path.splitext(cmrxml)[0])[0]}.NDVI.tif"
    band1_file = "code/new_test/HLS_VI.L30.T06WVS.2024120T211159.v2.0.NDVI.tif"
    cmr = untangle.parse(hls_vi_metadata)
    granule = cmr.Granule
    item_id = granule.GranuleUR.cdata
    datetime_str = granule.Temporal.RangeDateTime.BeginningDateTime.cdata
    item_datetime = datetime.datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%fZ")

    item_geometry = get_geometry(granule)
    multi = shape(item_geometry)
    item_bbox = list(multi.bounds)
    item = pystac.Item(
        id=item_id,
        datetime=item_datetime,
        geometry=item_geometry,
        bbox=item_bbox,
        properties={},
    )

    process_common_metadata(item, granule)
    process_eo(item, granule)
    add_assets(item, granule, endpoint, version)
    process_projection(item, granule, band1_file)
    process_view_geometry(item, granule)
    process_scientific(item, granule)
    # item.validate()
    feature = item.to_dict()
    return feature


def create_item(hls_vi_metadata, out_json, endpoint, version):

    hls_vi_metadata = hls_vi_metadata
    out_json = out_json
    endpoint = endpoint
    version = version
    item = cmr_to_item(hls_vi_metadata, endpoint, version)
    with open(out_json, "w") as outfile:
        json.dump(item, outfile)


if __name__ == "__main__":
    cmr_xml = "code/data/HLS-VI.L30.T06WVS.2024120T211159.v2.0.cmr.xml"
    output_json = "test_hls_base_updated.json"
    create_item(cmr_xml, output_json, "data.lpdaac.earthdatacloud.nasa.gov", "020")
