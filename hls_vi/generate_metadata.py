import getopt
import importlib_resources
import os
import sys
from xml.dom import minidom

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import rasterio
from lxml import etree as ET
from lxml.etree import Element, ElementBase


def generate_metadata(input_dir: Path, output_dir: Path) -> None:
    """
    Create CMR XML metadata file for an HLS VI granule.

    Args:
        input_dir:
            Directory containing files for an HLS granule.  It is assumed that
            the directory contains a metadata file named `HLS.*.cmr.xml`.
        output_dir:
            Directory containing files for an HLS VI granule corresponding to
            the input HLS granule.  The CMR XML metadata file will be written
            to this directory with the name `HLS-VI.*.cmr.xml`.
    """
    metadata_path = next(input_dir.glob("HLS.*.cmr.xml"))
    tree = ET.parse(str(metadata_path), None)

    with rasterio.open(next(output_dir.glob("*.tif"))) as vi_tif:
        tags = vi_tif.tags()

    processing_time = tags["HLS_VI_PROCESSING_TIME"]

    granule_ur = tree.find("GranuleUR")
    input_granule_ur = granule_ur.text
    granule_ur.text = granule_ur.text.replace("HLS", "HLS-VI")
    set_additional_attribute(
        tree.find("AdditionalAttributes"),
        "Input_HLS_GranuleUR",
        input_granule_ur,
    )

    time_format = "%Y-%m-%dT%H:%M:%S.%fZ"
    formatted_date = datetime.now(timezone.utc).strftime(time_format)
    tree.find("InsertTime").text = formatted_date
    tree.find("LastUpdate").text = formatted_date

    dataset_id = tree.find("Collection/DataSetId")
    dataset_id.text = (
        "HLS Operational Land Imager Vegetation Indices Daily Global 30 m V2.0"
        if "L30" in metadata_path.name
        else "HLS Sentinel-2 Multi-spectral Instrument Vegetation Indices Daily Global 30 m V2.0"  # noqa: E501
    )
    set_additional_attribute(
        tree.find("AdditionalAttributes"),
        "IDENTIFIER_PRODUCT_DOI",
        "10.5067/HLS/HLSL30_VI.002"
        if "L30" in metadata_path.name
        else "10.5067/HLS/HLSS30_VI.002",
    )
    normalize_additional_attributes(tree.find("AdditionalAttributes"))

    data_granule = tree.find("DataGranule")
    data_granule.remove(data_granule.find("DataGranuleSizeInBytes"))
    data_granule.find("ProductionDateTime").text = processing_time
    producer_granule_id = data_granule.find("ProducerGranuleId")
    producer_granule_id.text = producer_granule_id.text.replace("HLS", "HLS-VI")

    tree.find("DataFormat").text = "COG"

    append_fmask_online_access_urls(
        tree.find("OnlineAccessURLs"),
        input_granule_ur,
    )

    with (
        importlib_resources.files("hls_vi")
        / "schema"
        / "Granule.xsd"  # pyright: ignore[reportOperatorIssue]
    ).open() as xsd:
        ET.XMLSchema(file=xsd).assertValid(tree)

    # Python 3.9 or `lxml==4.5` add an `indent()` function to nicely format our XML
    # Alas we cannot use those yet, so rely on this approach using `xml.dom.minidom`
    dom = minidom.parseString(
        ET.tostring(tree, xml_declaration=True, pretty_print=False)
    )
    pretty_xml = os.linesep.join(
        [line for line in dom.toprettyxml(indent="  ").splitlines() if line.strip()]
    )

    dest = output_dir / metadata_path.name.replace("HLS", "HLS-VI")
    dest.write_text(pretty_xml, encoding="utf-8")


def normalize_additional_attributes(container: ElementBase) -> None:
    """Normalize additional attribute values.

    On rare occasions, granule data is split and recombined upstream.  When this
    occurs, the associated metadata is also split and recombined, resulting in values
    for additional attributes that are created by joining the separate parts with the
    string `" + "`.

    For example, the PROCESSING_BASELINE value of the HLS metadata resulting from this
    scenario might be `05.11 + 05.11` instead of simply `05.11`.  When the CMR contains
    data type constraints on these additional attribute values, such values can cause
    CMR to reject the metadata.  Continuing this example, when PROCESSING_BASELINE is
    constrained to `float` values, the string `05.11 + 05.11` will fail `float` parsing
    and the CMR will raise an error.

    Therefore, we must "normalize" such additional attribute values by simply splitting
    around the `" + "` and (arbitrarily) using the first value as the value of the
    additional attribute.
    """
    attr_els: List[ElementBase] = container.findall("./AdditionalAttribute", None)

    for attr_el in attr_els:
        normalize_additional_attribute(attr_el)


def normalize_additional_attribute(attr_el: ElementBase) -> None:
    values_el: ElementBase = attr_el.find("./Values", None)

    for el in iter(values_el):
        # Replace the text of the additional attribute value with the first value
        # obtained by splitting the text on " + ".  If the text does not contain
        # " + ", the text remains the same.  For example, "05.11".split(" + ") is
        # simply ["05.11"], so taking the first element simply produces "05.11".
        el.text = el.text.split(" + ", 1)[0].strip()


def set_additional_attribute(attrs: ElementBase, name: str, value: str) -> None:
    attr = attrs.find(f'./AdditionalAttribute[Name="{name}"]', None)

    if attr is not None:
        attr.find(".//Value").text = value
    else:
        attr = Element("AdditionalAttribute", None, None)
        attr_name = Element("Name", None, None)
        attr_name.text = name
        attr_values = Element("Values", None, None)
        attr_value = Element("Value", None, None)
        attr_value.text = value
        attr_values.append(attr_value)
        attr.append(attr_name)
        attr.append(attr_values)
        attrs.append(attr)


def append_fmask_online_access_urls(
    access_urls: ElementBase, hls_granule_ur: str
) -> None:
    """Include links to Fmask layer from HLS granule in metadata

    This is intended to help users find the relevant Fmask band without
    having to duplicate it into the HLS-VI product. See,
    https://github.com/NASA-IMPACT/hls-vi/issues/47
    """
    prefix = "HLSL30.020" if hls_granule_ur.startswith("HLS.L30") else "HLSS30.020"

    http_attr = Element("OnlineAccessURL", None, None)
    http_attr_url = Element("URL", None, None)
    http_attr_url.text = f"https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/{prefix}/{hls_granule_ur}/{hls_granule_ur}.Fmask.tif"  # noqa: E501
    http_attr_desc = Element("URLDescription", None, None)
    http_attr_desc.text = f"Download Fmask quality layer {hls_granule_ur}.Fmask.tif"
    http_attr.append(http_attr_url)
    http_attr.append(http_attr_desc)

    s3_attr = Element("OnlineAccessURL", None, None)
    s3_attr_url = Element("URL", None, None)
    s3_attr_url.text = (
        f"s3://lp-prod-protected/{prefix}/{hls_granule_ur}/{hls_granule_ur}.Fmask.tif"
    )
    s3_attr_desc = Element("URLDescription", None, None)
    s3_attr_desc.text = f"This link provides direct download access via S3 to the Fmask quality layer {hls_granule_ur}.Fmask.tif"  # noqa: E501
    s3_attr.append(s3_attr_url)
    s3_attr.append(s3_attr_desc)

    access_urls.append(http_attr)
    access_urls.append(s3_attr)


def parse_args() -> Tuple[Path, Path]:
    short_options = "i:o:"
    long_options = ["instrument=", "inputdir=", "outputdir="]
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


def main() -> None:
    input_dir, output_dir = parse_args()
    generate_metadata(input_dir=input_dir, output_dir=output_dir)


if __name__ == "__main__":
    main()
