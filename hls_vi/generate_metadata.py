import getopt
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import rasterio


def generate_metadata(input_dir: Path, output_dir: Path):
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
    tree = ET.parse(metadata_path)

    with rasterio.open(next(output_dir.glob("*.tif"))) as vi_tif:
        sensing_times = vi_tif.tags()["SENSING_TIME"].split(";")
        sensing_time_begin, sensing_time_end = sensing_times[0], sensing_times[-1]
        processing_time = vi_tif.tags()["HLS_VI_PROCESSING_TIME"]

    granule_ur = tree.find("GranuleUR")
    granule_ur.text = granule_ur.text.replace("HLS", "HLS-VI")

    time_format = "%Y-%m-%dT%H:%M:%S.%fZ"
    formatted_date = datetime.now(timezone.utc).strftime(time_format)
    tree.find("InsertTime").text = formatted_date
    tree.find("LastUpdate").text = formatted_date

    # TODO: Find out what the Collection ID should be
    tree.find("Collection/DataSetId").text = "Update HLS-VI New Collection ID String"

    data_granule = tree.find("DataGranule")
    data_granule.remove(data_granule.find("DataGranuleSizeInBytes"))
    data_granule.find("ProductionDateTime").text = processing_time
    producer_granule_id = data_granule.find("ProducerGranuleId")
    producer_granule_id.text = producer_granule_id.text.replace("HLS", "HLS-VI")

    tree.find("Temporal/RangeDateTime/BeginningDateTime").text = sensing_time_begin
    tree.find("Temporal/RangeDateTime/EndingDateTime").text = sensing_time_end

    tree.write(
        output_dir / metadata_path.name.replace("HLS", "HLS-VI"),
        encoding="utf-8",
        xml_declaration=True,
    )


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


def main():
    input_dir, output_dir = parse_args()
    generate_metadata(input_dir=input_dir, output_dir=output_dir)


if __name__ == "__main__":
    main()
