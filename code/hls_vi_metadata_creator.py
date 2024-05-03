import os
import datetime
import rasterio

import xml.etree.ElementTree as ET


"""
usage python hls_vi-metadata_creator hls_base_granule.xml hls-vi.XYZ.NDVI.tif

TO Do:
## validate against echo10 schema before writing XML
## Update DataGranuleSizeInBytes - this is the HLS VI granule size : int(os.path.getsize(HLS_VI granule))
## Update HLS Production date time
## Udpate DataSetId (from LPDAAC)
## 

"""

hls_metadata = "./templates/HLS.L30.T11SPS.2022001T181028.v2.0.cmr.xml"

## read an example HLS granule -- REPLACE THIS WITH NDVI VI granule
test_hls_granule = "./HLS.S30.T30VUH.2018178T113319.v2.0.B8A.tif"
dataset = rasterio.open(test_hls_granule)
dataset_tags = dataset.tags()
## extract metadata atribute
sensing_time = dataset_tags["SENSING_TIME"].split(";")


source_tree = ET.parse(hls_metadata)

# update this to copy
dest_tree = source_tree

source_root = source_tree.getroot()
dest_root = dest_tree.getroot()


## GranuleUR
dest_tree.find('GranuleUR').text = dest_tree.find('GranuleUR').text.replace("HLS", "HLS-VI")

## Temporal Values
time_format = "%Y-%m-%dT%H:%M:%S.%fZ"
dest_tree.find("InsertTime").text = datetime.datetime.utcnow().strftime(time_format)

# This needs to be updated to last update time of file
dest_tree.find("LastUpdate").text = datetime.datetime.utcnow().strftime(time_format)

## Collection
collection = dest_root.find("Collection")
collection.find("DataSetId").text =  "Update HLS-VI New Collection ID String"

## DataGranule
version_id = dest_tree.find('GranuleUR').text[-3:]
data_granule = dest_root.find("DataGranule")
data_granule.find("DataGranuleSizeInBytes").text =  "XYZ"
data_granule.find("ProducerGranuleId").text = dest_tree.find('GranuleUR').text[:-5]
data_granule.find("ProductionDateTime").text = "UPDATE HLS Prodution DATETIME"
data_granule.find("LocalVersionId").text = version_id


## Temporal
temporal =  dest_root.find("Temporal")
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
temporal.find("RangeDateTime").find("EndingDateTime").text = end_time.strftime(time_format)

        
## write the HLS-Vi metadata
dest_tree.write(hls_metadata.replace("HLS", "HLS-VI"), encoding='utf-8', xml_declaration=True)
