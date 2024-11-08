from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional, Tuple
from xml.etree import ElementTree as ET
import contextlib
import io
import json

import pytest
import rasterio
from hls_vi.generate_metadata import generate_metadata
from hls_vi.generate_indices import (
    Granule,
    Index,
    generate_vi_granule,
)
from hls_vi.generate_stac_items import create_item

ISO_8601_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def find_index_by_long_name(long_name: str) -> Index:
    for index in Index:
        if index.long_name == long_name:
            return index
    raise ValueError(f"Index with longname '{long_name}' not found")


def assert_tifs_equal(granule: Granule, actual: Path, expected: Path):
    with rasterio.open(actual) as actual_src:
        with rasterio.open(expected) as expected_src:
            assert actual_src.count == expected_src.count
            assert actual_src.width == expected_src.width
            assert actual_src.height == expected_src.height
            assert actual_src.bounds == expected_src.bounds
            assert actual_src.crs == expected_src.crs
            assert actual_src.transform == expected_src.transform

            index = find_index_by_long_name(actual_src.tags()["long_name"])
            index_data = index(granule.data).filled()
            actual_data = actual_src.read()
            expected_data = expected_src.read()

            assert (actual_data == index_data).all()
            assert (actual_data == expected_data).all()

            actual_tags, actual_time_str = remove_item(
                actual_src.tags(), "HLS_VI_PROCESSING_TIME"
            )
            expected_tags, expected_time_str = remove_item(
                expected_src.tags(), "HLS_VI_PROCESSING_TIME"
            )

            assert actual_tags == expected_tags
            assert actual_time_str is not None
            assert expected_time_str is not None

            actual_time = datetime.strptime(actual_time_str, ISO_8601_DATETIME_FORMAT)
            expected_time = datetime.strptime(
                expected_time_str, ISO_8601_DATETIME_FORMAT
            )

            # The actual time should be greater than the expected time because
            # the actual time is the time when the VI was generated (now, during
            # test execution), which is after the time when the expected VI was
            # generated (as a test fixture).
            assert actual_time > expected_time


def remove_item(
    mapping: Mapping[str, str], key: str
) -> Tuple[Mapping[str, str], Optional[str]]:
    return {k: v for k, v in mapping.items() if k != key}, mapping.get(key)


def remove_element(root: ET.Element, path: str) -> ET.Element:
    parent_path = "/".join(path.split("/")[:-1])
    parent = root.find(parent_path)
    child = root.find(path)

    assert parent is not None
    assert child is not None

    parent.remove(child)

    return child


def remove_datetime_elements(tree: ET.ElementTree) -> ET.ElementTree:
    root = tree.getroot()

    for path in (
        "./InsertTime",
        "./LastUpdate",
        "./DataGranule/ProductionDateTime",
        "./Temporal/RangeDateTime/BeginningDateTime",
        "./Temporal/RangeDateTime/EndingDateTime",
    ):
        remove_element(root, path)

    return tree


def assert_indices_equal(granule: Granule, actual_dir: Path, expected_dir: Path):
    actual_tif_paths = sorted(actual_dir.glob("*.tif"))
    actual_tif_names = [path.name for path in actual_tif_paths]
    expected_tif_paths = sorted(expected_dir.glob("*.tif"))
    expected_tif_names = [path.name for path in expected_tif_paths]

    assert actual_tif_names == expected_tif_names

    for actual_tif_path, expected_tif_path in zip(actual_tif_paths, expected_tif_paths):
        assert_tifs_equal(granule, actual_tif_path, expected_tif_path)


@pytest.mark.parametrize(
    argnames="input_dir,id_str",
    argvalues=[
        (
            "tests/fixtures/HLS.L30.T06WVS.2024120T211159.v2.0",
            "HLS.L30.T06WVS.2024120T211159.v2.0",
        ),
        (
            "tests/fixtures/HLS.S30.T13RCN.2024128T173909.v2.0",
            "HLS.S30.T13RCN.2024128T173909.v2.0",
        ),
    ],
)
def test_generate_indices(input_dir, id_str, tmp_path: Path):
    granule = generate_vi_granule(Path(input_dir), tmp_path, id_str)
    assert_indices_equal(granule, tmp_path, Path(input_dir.replace("HLS", "HLS-VI")))
    assert (tmp_path / f"{id_str.replace('HLS', 'HLS-VI')}.jpg").exists()


@pytest.mark.parametrize(
    argnames="input_dir,output_dir",
    argvalues=[
        (
            "tests/fixtures/HLS.L30.T06WVS.2024120T211159.v2.0",
            "tests/fixtures/HLS-VI.L30.T06WVS.2024120T211159.v2.0",
        ),
        (
            "tests/fixtures/HLS.S30.T13RCN.2024128T173909.v2.0",
            "tests/fixtures/HLS-VI.S30.T13RCN.2024128T173909.v2.0",
        ),
    ],
)
def test_generate_cmr_metadata(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    input_cmr_xml_path = next(input_path.glob("HLS.*.cmr.xml"))
    output_cmr_xml_basename = input_cmr_xml_path.name.replace("HLS", "HLS-VI")
    actual_metadata_path = output_path / output_cmr_xml_basename

    # We keep the expected metadata file outside of the output directory,
    # otherwise it would be overwritten by the actual metadata file.
    expected_metadata_path = Path("tests/fixtures") / output_cmr_xml_basename

    try:
        generate_metadata(input_dir=input_path, output_dir=output_path)

        actual_metadata_tree = remove_datetime_elements(ET.parse(actual_metadata_path))
        expected_metadata_tree = remove_datetime_elements(
            ET.parse(expected_metadata_path)
        )

        actual_metadata = io.BytesIO()
        actual_metadata_tree.write(actual_metadata, encoding="utf-8")

        expected_metadata = io.BytesIO()
        expected_metadata_tree.write(expected_metadata, encoding="utf-8")

        assert (
            actual_metadata.getvalue().decode() == expected_metadata.getvalue().decode()
        )
    finally:
        with contextlib.suppress(FileNotFoundError):
            actual_metadata_path.unlink()


def test_generate_stac_items(tmp_path):
    import shutil

    # Since we our HLS-VI CMR XML fixture files are not in the same directory as the
    # corresponding NDVI TIF files, we need to copy the NDVI TIF files to the temporary
    # directory, along with the CMR XML file, so that they are both in the same
    # directory.  This is because our logic for creating STAC items assumes that the
    # CMR XML file and the NDVI TIF file are in the same directory.

    cmr_xml = "HLS-VI.L30.T06WVS.2024120T211159.v2.0.cmr.xml"
    ndvi_tif = cmr_xml.replace("cmr.xml", "NDVI.tif")
    fixtures = Path("tests") / "fixtures"
    shutil.copy(fixtures / cmr_xml, tmp_path / cmr_xml)
    shutil.copy(fixtures / ndvi_tif.rstrip(".NDVI.tif") / ndvi_tif, tmp_path / ndvi_tif)

    temp_json_output = tmp_path / "temp_output.json"

    create_item(
        str(tmp_path / cmr_xml),
        temp_json_output,
        "data.lpdaac.earthdatacloud.nasa.gov",
        "020",
    )

    with open("tests/fixtures/HLS-VI_stac_item.json") as f:
        expected_stac_item = json.load(f)
    with open(temp_json_output) as f:
        actual_stac_item = json.load(f)
    assert actual_stac_item == expected_stac_item
