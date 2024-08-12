import getopt
import importlib_resources
import os
import re
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import rasterio
from lxml import etree as ET
from lxml.etree import Element, ElementBase


def parse_sensing_time(sensing_time: str) -> Tuple[str, str]:
    """Parse SENSING_TIME tag value into (start, end) tuple.

    Expect `sensing_time` in one of the following forms, where each `DT` is an ISO 8601
    combined date and time representation, with a `Z` suffix (and optional whitespace
    surrounding `+` and `;` separators):

    - `DT`
    - `DT; DT`
    - `DT + DT; DT`
    - `DT; DT + DT`
    - `DT + DT; DT + DT`

    Sort all `DT` values in ascending order and return the min and max, respectively,
    in a tuple.  When only one `DT` value is specified, both values in the tuple are
    the same value.

    Examples:

    >>> parse_sensing_time("2024-04-29T21:11:59.7221750Z")
    ('2024-04-29T21:11:59.7221750Z', '2024-04-29T21:11:59.7221750Z')
    >>> parse_sensing_time(";2024-04-29T21:11:59.7221750Z")
    ('2024-04-29T21:11:59.7221750Z', '2024-04-29T21:11:59.7221750Z')
    >>> parse_sensing_time("2024-04-29T21:11:59.7221750Z;")
    ('2024-04-29T21:11:59.7221750Z', '2024-04-29T21:11:59.7221750Z')
    >>> parse_sensing_time("2024-04-29T21:11:59.7221750Z+")
    ('2024-04-29T21:11:59.7221750Z', '2024-04-29T21:11:59.7221750Z')
    >>> parse_sensing_time(
    ... "2024-04-29T21:12:59.7221750Z ; 2024-04-29T21:11:59.7221750Z"
    ... )
    ('2024-04-29T21:11:59.7221750Z', '2024-04-29T21:12:59.7221750Z')
    >>> parse_sensing_time(
    ... "2024-04-29T21:12:59.7221750Z + 2024-04-29T21:11:59.7221750Z;"
    ... )
    ('2024-04-29T21:11:59.7221750Z', '2024-04-29T21:12:59.7221750Z')
    >>> parse_sensing_time(
    ... ";2024-04-29T21:12:59.7221750Z + 2024-04-29T21:11:59.7221750Z"
    ... )
    ('2024-04-29T21:11:59.7221750Z', '2024-04-29T21:12:59.7221750Z')
    >>> parse_sensing_time(
    ... "2024-04-29T21:10:59.7221750Z;"
    ... "2024-04-29T21:12:59.7221750Z + 2024-04-29T21:11:59.7221750Z;"
    ... )
    ('2024-04-29T21:10:59.7221750Z', '2024-04-29T21:12:59.7221750Z')
    >>> parse_sensing_time(
    ... "2024-04-29T21:12:59.7221750Z+2024-04-29T21:11:59.7221750Z;"
    ... "2024-04-29T21:10:59.7221750Z + 2024-04-29T21:11:59.7221750Z;"
    ... )
    ('2024-04-29T21:10:59.7221750Z', '2024-04-29T21:12:59.7221750Z')
    """
    sensing_times = sorted(
        t.strip() for t in re.split("[+;]", sensing_time) if t.strip()
    )
    return sensing_times[0], sensing_times[-1]


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
    tree = ET.parse(str(metadata_path))

    with rasterio.open(next(output_dir.glob("*.tif"))) as vi_tif:
        tags = vi_tif.tags()

    sensing_time_begin, sensing_time_end = parse_sensing_time(tags["SENSING_TIME"])
    processing_time = tags["HLS_VI_PROCESSING_TIME"]

    granule_ur = tree.find("GranuleUR")
    granule_ur.text = granule_ur.text.replace("HLS", "HLS-VI")

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

    data_granule = tree.find("DataGranule")
    data_granule.remove(data_granule.find("DataGranuleSizeInBytes"))
    data_granule.find("ProductionDateTime").text = processing_time
    producer_granule_id = data_granule.find("ProducerGranuleId")
    producer_granule_id.text = producer_granule_id.text.replace("HLS", "HLS-VI")

    tree.find("Temporal/RangeDateTime/BeginningDateTime").text = sensing_time_begin
    tree.find("Temporal/RangeDateTime/EndingDateTime").text = sensing_time_end

    with (importlib_resources.files("hls_vi") / "schema" / "Granule.xsd").open() as xsd:
        ET.XMLSchema(file=xsd).assertValid(tree)

    tree.write(
        str(output_dir / metadata_path.name.replace("HLS", "HLS-VI")),
        encoding="utf-8",
        xml_declaration=True,
    )


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
