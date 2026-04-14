import concurrent.futures
from pathlib import Path

import click
import pandas as pd
from google.cloud import bigquery, storage
from loguru import logger

QUERY_STRS = {}
QUERY_STRS["original"] = """
DECLARE TARGET_TENANT_ID STRING DEFAULT "8d8232f3-010d-4857-bf20-0cc7dc42ad97";

WITH original_files AS
(
  SELECT
    DISTINCT tenant_id, original_id, original_file_category_display_name
  FROM
    `esperanto-drawer-prod.dw_product._stg_entbizdev_dim_drawing`
  WHERE
    tenant_id = TARGET_TENANT_ID
), original_file_paths AS
(
  SELECT
    id as original_id,
    file_name as file_name,
    total_pages as original_total_pages,
    REPLACE(file_path, "gs://zoolake-prod.appspot.com/", "") as original_gcs_blob_path,
    FORMAT(
        "%s/%s.%s",
        TARGET_TENANT_ID,
        id,
        CASE
            WHEN file_type = "Pdf" THEN 'pdf'
            WHEN file_type = "Png" THEN 'png'
            WHEN file_type = "Jpeg" THEN "jpg"
          ELSE 'tiff'
        END
    ) as original_local_path,
    file_category_id,
    file_type
  FROM
    `esperanto-drawer-prod.dl_catalyst_alloydb.catalyst_original_file`
  WHERE
    tenant_id = TARGET_TENANT_ID
)

SELECT
  *
FROM
  original_files
LEFT JOIN original_file_paths USING(original_id)
WHERE
  original_id IN (
    -- トライアル不具合関連情報
    "fa6addba-b5f2-4dfd-900e-54384ef393b8",
    "ee7abf0e-7aa3-4f0c-b958-3e262b42ff74",
    "d3898fb6-dcc1-4593-8ec5-55beed2e8c6b",
    "bfbf8a9c-ddf0-436d-b1c5-046adcca318b",
    "0bc61ce7-ba72-40e4-b9c0-87474e7020fe",
    "65514489-f6ad-47ba-a7af-1aa5be430d32",
    "d8ff0d97-8bf9-47f9-828d-9ef9bd410cfa",
    "a03ddc18-88fb-40f8-9ac4-f8357bcb6020",
    "3f64c803-1eb5-463a-a1a9-760416007a51",
    "d92d1d4b-a705-4740-8d9e-69d73df1b768",
    "fb197486-861f-4f1e-b8ab-6860e1fa50ac",
    "4077d6db-036b-4a7c-8706-27b2c02ef9b9",
    "38306a4a-ec8a-4afc-924a-28d496425fde",
    "d19f68af-7536-4e8b-a182-1a477cda83e7",
    "d3bc452c-ef4e-41a0-9ed0-a09009df0941",
    "93c66ea2-a573-4939-8e98-77cf1930b662",
    "4ac5918c-6d27-44be-987c-b6304c7fe5d7",
    "0135abcf-5a7a-4ad0-b578-d336b97a71c8",
    "25185e3a-9afd-42fe-be96-99751e8d0236",
    "e5a1642c-8fea-4a3c-acdf-bf33d811b714",
    "3b5cf8fa-3857-4307-bf0a-8fcd25d8ea1b",
    "b1bbdb35-5628-4777-af95-ec11471834d5",
    "3821f4c5-1a55-44ee-88a2-bf0e0e5d596b",
    "f66d1242-5bf6-40cb-b5c5-cd321df5a38e",
    "a8318222-972f-4bb1-b9fe-e5eab9a9d6e4",
    "0857cb29-9727-4b7b-9aef-e0a73f1d3464",
    "3177c427-8abb-4f8e-bee2-e799290e2fdc",
    "a8c85dcd-7e74-4b21-8c0e-b757dabe8358",
    "436a0b41-725c-4f50-829a-61e87023538d",
    "173578cc-4b38-48e9-819e-79000bb5cb1b",
    "a83d5a29-4161-4d15-85ef-f95a4c362d6d",
    "0648f0b2-b59d-445d-966d-8f66a33d38ea",
    "67f50195-f002-48ab-aa80-0878d86d8bf3",
    "5d0645e3-c2c4-4674-b19f-bd585d3cde0d",
    "ec572178-ec3d-4051-996c-1721e838cad8",
    "511cf3ef-b343-43ed-aacd-f475ea2d7948",
    "a3c357b3-ce9a-4f4c-a0fc-21edf502d088",
    "c4963864-5f10-40f6-9f4e-b970e32f4782",
    "d43fae4d-8ba8-480b-bd5a-29a243e897fb",
    "390e717d-6511-47c4-851f-e674896f1bce",
    "8f95c6ff-708e-427d-ae31-381c8d25ec56",
    "decf10ae-bd11-4e2b-82f6-96e146846ba3",
    "06bda852-4b83-4a44-8de9-6ab1898b1ce6",
    "1cdc8bad-dc79-4ffe-8ad9-100bf23b3d1b",
    "46534347-3892-4f54-9ffe-f31d8ec31d20",
    "c56636ee-cadf-43f2-9569-a62442d496ec",
    "a768a6c6-da08-428a-b76f-ce41923d0fca",
    "b67d921f-9dea-43a1-b908-a51f5173c287",
    "469c5b96-6458-4c6d-a49f-c5c884e601ac",
    "0e09c279-df36-4f11-9ff1-53a2e129456a",
    "aa75159-71ac-4268-a547-b75ceac46ab0",
    "6253bdbd-444d-41fa-ae99-e9208874b519",
    "6334c6d7-dceb-4250-9f37-39343a60d747",
    "5449ca06-fb32-44ef-af47-3720e6a29e8a",
    "82bbf368-18e4-4fec-8d3e-7fbb1aee3114",
    "d176f396-7a1b-4f3f-9dc2-ca6e414a7177",
    "2bd33480-89c7-4dec-a6c5-11c92eb39004",
    "13b48c24-fb96-437d-bc06-47df34e8363a",
    "aaf5dffa-87e4-4632-9e1b-e70355486f93",
    "4f74a4fa-01fe-4ddc-b81c-d56cdb6de5f7",
    "e7c9afd9-1f85-4ca9-8813-6e68040a7b16",
    "5385146a-4baf-4471-9664-2100737b66c4",
    "10b01cd1-47ab-4fb7-9233-73b02c4955c2",
    "9ea9a902-8a26-4b27-9b77-5e85dcc3db30",
    "16bbde91-8d30-4091-898a-493b8ebbd872",
    "933414ab-96c7-4b74-a84d-d5ae7d4d5d8c",
    "72d17346-6691-4580-ab8e-926c1c8f7be5",
    "c2992124-1648-473d-ba15-2f4cf1b440e5",
    "cfc9410f-2a6b-40cf-bb48-5bed1f250941",
    "b9166450-b219-4b83-b94e-96ecbd48dc0c",
    "b520964c-4585-4446-a13c-a501e9aca60e",
    "fdaa15ba-3323-403b-aad8-ab37bb851d04",
    "86036edc-026f-408a-803f-7d3d12e5f50d",
    "955fec23-e48e-4454-af65-17fc53ebb3fe",
    "f10acf97-e442-4562-b939-5bfbb7082d0b",
    "0af10d5a-4d8d-40be-9fe6-00f434759fad",
    "84d24565-bfb1-4873-9b69-b948614429a3",
    "95a5eb60-1e25-47cc-ab32-10f7255df6e1",
    "ee77f8a1-42ee-434e-82a8-f7d441afef32",
    "ef058eef-620d-46cf-9bc7-7d6511222e12",
    "01197872-b556-42c5-988e-a522b75eaade",
    "6004890b-dce7-44cd-9293-63cdc033384d",
    "da792ccb-0290-4ca1-8aa2-2d89c5d6efc9",
    "acbe7a55-3b66-450b-abc7-98a348a33671",
    "215b8507-c73a-4664-81f3-89b0650cb75c",
    "df1e766d-a406-47b1-a067-3851ea773135",
    "e46e3c7e-7c9a-47cc-86c4-2a9df07ff34e",
    "2afab49b-db0c-420c-9cd8-69797fa8832d",
    "56210631-37d7-48eb-9ced-66f1181c0cf5",
    "2042ad4f-2002-41f5-a084-5da7dabfed56",
    "ca772734-85d2-4887-8f9b-579fa0c97db2",
    "2b9465f6-56c5-40f7-a78d-43038edec09c",
    "8373f31c-3aa9-49b3-b8fb-22a8459d2193",
    "403b02e4-f47c-49f4-b1c7-1c253462bd6e",
    "b4c77871-ee29-4edb-b2b4-de1ee47133fc",
    "c9fb644a-87a1-4c59-b149-f109aa95bbb1",
    "9ddd970d-16d9-4ea5-91b8-d06353896911",
    "6412598f-2e21-4972-a432-54f9257a615a",
    "2b1ae06c-b7bd-4542-ac4d-7ff5e2862d24",
    "64e80ee1-530e-45fa-ab80-c97de82e7f22",
    "59c5ea64-68dc-494b-bc00-b0844ff8b59a",
    "6d0affcc-b352-4bd0-b189-d36ff2ecbee0",
    "811dd87e-ca90-4f2c-a1e3-4872de0af6b1",
    "9880a256-47a9-4461-9784-db54ead377c0",
    "57ad3c7a-c6d7-4218-90dc-6691eae563fb",
    "18ceeeaf-65ce-4747-8aaa-37c2429300bd",
    "f4b8b914-11a5-46c8-a367-fccfc156af83",
    "c3bad53c-fb84-4eda-8482-786c9dbc2276",
    "7e420d78-e63f-4a5d-bead-bc4f0e94ba3a",
    "88d2928d-84ed-45c9-ac53-01da9f8329fc",
    "e6d50c03-6f27-419e-88bc-82a7f63da55a",
    "30f112ad-14a4-48d2-98f2-049a593f284e",
    "26faaf7d-9cd0-4ab6-a3f8-350b62a8c6fc",
    "27be5516-4c7c-4551-bbce-63f3891b74eb",
    "eb3c20cb-1318-4dce-8c34-e646fe4897e1",
    "7d871f4b-ddb5-4473-b1ca-0b639a1af020",
    "3b86e144-b6a1-4586-bd58-803ed4e2a4c7",
    "42b4a65f-3086-483e-b2ee-bde995eae2f8",
    "07c5a4bd-9caa-41a1-85e5-9133861421ee",
    "f374c9d1-361f-498e-ac47-89bd43423ee6",
    "723fb9e3-2ee8-43ba-8454-accaf07b9f47",
    "7419a865-e0f2-4562-a78f-b3ef3a839a16",
    "fa7548f3-f760-49ee-871e-90544fc129cf",
    "fafead5a-7f1e-4fd7-9b30-e07331e11587",
    "3718fd91-e93e-4021-af70-524ba315acab",
    "f5d0c563-d68a-440e-a30f-fcdbfe56dea1",
    "62c5786d-6cf7-42e6-8011-18b1550b52db",
    "45dc3788-9b38-485d-bf1b-7ee6296596d8",
    "eb71351b-0f7c-4900-89b1-07bb9da6e9da",
    "bb2a9254-55b3-4fa6-91cd-d3da6808fd57",
    "97c627ab-9fbb-470d-ba9c-4aff4ae8e1b6",
    "5a90786f-0229-407f-b6a7-d3d30530b1d9",
    "f0ea875f-fd42-4245-881b-280d9c7ccbe0",
    "a9f94805-9f41-4fef-85a8-b969abcb37c4",
    "d910fbee-9a77-4ec4-8e68-d6d439c81d78",
    "966c704f-8f0e-4ed1-a457-4fa0cea545d2",
    "ebbcce82-17bd-4c90-a133-9195dd9f5a51",
    "f49ff69f-b56a-4d34-93a5-04364ed9bfa9",
    "5efd0041-eb1f-4cda-b09c-5c08a092b3fe",
    "f73a1e57-6c31-4c43-87c8-ad9969d4e7b0",
    "e190cdaa-c270-4159-b6e4-d400f505441c",
    "8e758f51-68e1-4f27-9114-b46cdd0cdf7e",
    -- トライアル設計レビュー情報
    "e5efe9cc-f1d3-417a-9252-d7dc9b93e268",
    "abbf9c85-ca03-4e5a-9a59-3ea53e732a82",
    "bc1121ee-7405-4b82-9154-ce0bcf911623",
    "253ec530-e512-4118-a40c-f0e646006838",
    "d45ae805-bc34-43c7-aa11-8171e5194612",
    "926834cd-b6e2-4afa-ae48-7539adcc4ce9",
    "b32f28ba-5363-42c7-bc21-2049dbc350b5",
    "79fba2cf-57a6-453d-abcf-febb9f2e0ea9",
    "b3d8a510-563c-4249-9655-608d33dbb4d0",
    "612258e0-67ea-4806-a997-89202d579a9e",
    "bdc0e3e4-9b84-4697-915b-80cb71838a74",
    "e5c01970-de1b-44b2-b9ab-7b38d5e570b8",
    "a68a1f51-292d-4e12-8f4f-20477879967b",
    "540bcfc4-122a-44fd-b9bd-c509e0dc81f6",
    "7636ca45-5fba-4ddd-b873-16008301daee"
)
"""

QUERY_STRS["drawing"] = """
WITH drawing AS
(
  SELECT
    id as drawing_id,
    original_id,
    page_number
  FROM
    `esperanto-drawer-prod.dl_catalyst_alloydb.catalyst_drawing_page`
  WHERE
    original_id IN (
      -- トライアル不具合関連情報
      "fa6addba-b5f2-4dfd-900e-54384ef393b8",
      "ee7abf0e-7aa3-4f0c-b958-3e262b42ff74",
      "d3898fb6-dcc1-4593-8ec5-55beed2e8c6b",
      "bfbf8a9c-ddf0-436d-b1c5-046adcca318b",
      "0bc61ce7-ba72-40e4-b9c0-87474e7020fe",
      "65514489-f6ad-47ba-a7af-1aa5be430d32",
      "d8ff0d97-8bf9-47f9-828d-9ef9bd410cfa",
      "a03ddc18-88fb-40f8-9ac4-f8357bcb6020",
      "3f64c803-1eb5-463a-a1a9-760416007a51",
      "d92d1d4b-a705-4740-8d9e-69d73df1b768",
      "fb197486-861f-4f1e-b8ab-6860e1fa50ac",
      "4077d6db-036b-4a7c-8706-27b2c02ef9b9",
      "38306a4a-ec8a-4afc-924a-28d496425fde",
      "d19f68af-7536-4e8b-a182-1a477cda83e7",
      "d3bc452c-ef4e-41a0-9ed0-a09009df0941",
      "93c66ea2-a573-4939-8e98-77cf1930b662",
      "4ac5918c-6d27-44be-987c-b6304c7fe5d7",
      "0135abcf-5a7a-4ad0-b578-d336b97a71c8",
      "25185e3a-9afd-42fe-be96-99751e8d0236",
      "e5a1642c-8fea-4a3c-acdf-bf33d811b714",
      "3b5cf8fa-3857-4307-bf0a-8fcd25d8ea1b",
      "b1bbdb35-5628-4777-af95-ec11471834d5",
      "3821f4c5-1a55-44ee-88a2-bf0e0e5d596b",
      "f66d1242-5bf6-40cb-b5c5-cd321df5a38e",
      "a8318222-972f-4bb1-b9fe-e5eab9a9d6e4",
      "0857cb29-9727-4b7b-9aef-e0a73f1d3464",
      "3177c427-8abb-4f8e-bee2-e799290e2fdc",
      "a8c85dcd-7e74-4b21-8c0e-b757dabe8358",
      "436a0b41-725c-4f50-829a-61e87023538d",
      "173578cc-4b38-48e9-819e-79000bb5cb1b",
      "a83d5a29-4161-4d15-85ef-f95a4c362d6d",
      "0648f0b2-b59d-445d-966d-8f66a33d38ea",
      "67f50195-f002-48ab-aa80-0878d86d8bf3",
      "5d0645e3-c2c4-4674-b19f-bd585d3cde0d",
      "ec572178-ec3d-4051-996c-1721e838cad8",
      "511cf3ef-b343-43ed-aacd-f475ea2d7948",
      "a3c357b3-ce9a-4f4c-a0fc-21edf502d088",
      "c4963864-5f10-40f6-9f4e-b970e32f4782",
      "d43fae4d-8ba8-480b-bd5a-29a243e897fb",
      "390e717d-6511-47c4-851f-e674896f1bce",
      "8f95c6ff-708e-427d-ae31-381c8d25ec56",
      "decf10ae-bd11-4e2b-82f6-96e146846ba3",
      "06bda852-4b83-4a44-8de9-6ab1898b1ce6",
      "1cdc8bad-dc79-4ffe-8ad9-100bf23b3d1b",
      "46534347-3892-4f54-9ffe-f31d8ec31d20",
      "c56636ee-cadf-43f2-9569-a62442d496ec",
      "a768a6c6-da08-428a-b76f-ce41923d0fca",
      "b67d921f-9dea-43a1-b908-a51f5173c287",
      "469c5b96-6458-4c6d-a49f-c5c884e601ac",
      "0e09c279-df36-4f11-9ff1-53a2e129456a",
      "aa75159-71ac-4268-a547-b75ceac46ab0",
      "6253bdbd-444d-41fa-ae99-e9208874b519",
      "6334c6d7-dceb-4250-9f37-39343a60d747",
      "5449ca06-fb32-44ef-af47-3720e6a29e8a",
      "82bbf368-18e4-4fec-8d3e-7fbb1aee3114",
      "d176f396-7a1b-4f3f-9dc2-ca6e414a7177",
      "2bd33480-89c7-4dec-a6c5-11c92eb39004",
      "13b48c24-fb96-437d-bc06-47df34e8363a",
      "aaf5dffa-87e4-4632-9e1b-e70355486f93",
      "4f74a4fa-01fe-4ddc-b81c-d56cdb6de5f7",
      "e7c9afd9-1f85-4ca9-8813-6e68040a7b16",
      "5385146a-4baf-4471-9664-2100737b66c4",
      "10b01cd1-47ab-4fb7-9233-73b02c4955c2",
      "9ea9a902-8a26-4b27-9b77-5e85dcc3db30",
      "16bbde91-8d30-4091-898a-493b8ebbd872",
      "933414ab-96c7-4b74-a84d-d5ae7d4d5d8c",
      "72d17346-6691-4580-ab8e-926c1c8f7be5",
      "c2992124-1648-473d-ba15-2f4cf1b440e5",
      "cfc9410f-2a6b-40cf-bb48-5bed1f250941",
      "b9166450-b219-4b83-b94e-96ecbd48dc0c",
      "b520964c-4585-4446-a13c-a501e9aca60e",
      "fdaa15ba-3323-403b-aad8-ab37bb851d04",
      "86036edc-026f-408a-803f-7d3d12e5f50d",
      "955fec23-e48e-4454-af65-17fc53ebb3fe",
      "f10acf97-e442-4562-b939-5bfbb7082d0b",
      "0af10d5a-4d8d-40be-9fe6-00f434759fad",
      "84d24565-bfb1-4873-9b69-b948614429a3",
      "95a5eb60-1e25-47cc-ab32-10f7255df6e1",
      "ee77f8a1-42ee-434e-82a8-f7d441afef32",
      "ef058eef-620d-46cf-9bc7-7d6511222e12",
      "01197872-b556-42c5-988e-a522b75eaade",
      "6004890b-dce7-44cd-9293-63cdc033384d",
      "da792ccb-0290-4ca1-8aa2-2d89c5d6efc9",
      "acbe7a55-3b66-450b-abc7-98a348a33671",
      "215b8507-c73a-4664-81f3-89b0650cb75c",
      "df1e766d-a406-47b1-a067-3851ea773135",
      "e46e3c7e-7c9a-47cc-86c4-2a9df07ff34e",
      "2afab49b-db0c-420c-9cd8-69797fa8832d",
      "56210631-37d7-48eb-9ced-66f1181c0cf5",
      "2042ad4f-2002-41f5-a084-5da7dabfed56",
      "ca772734-85d2-4887-8f9b-579fa0c97db2",
      "2b9465f6-56c5-40f7-a78d-43038edec09c",
      "8373f31c-3aa9-49b3-b8fb-22a8459d2193",
      "403b02e4-f47c-49f4-b1c7-1c253462bd6e",
      "b4c77871-ee29-4edb-b2b4-de1ee47133fc",
      "c9fb644a-87a1-4c59-b149-f109aa95bbb1",
      "9ddd970d-16d9-4ea5-91b8-d06353896911",
      "6412598f-2e21-4972-a432-54f9257a615a",
      "2b1ae06c-b7bd-4542-ac4d-7ff5e2862d24",
      "64e80ee1-530e-45fa-ab80-c97de82e7f22",
      "59c5ea64-68dc-494b-bc00-b0844ff8b59a",
      "6d0affcc-b352-4bd0-b189-d36ff2ecbee0",
      "811dd87e-ca90-4f2c-a1e3-4872de0af6b1",
      "9880a256-47a9-4461-9784-db54ead377c0",
      "57ad3c7a-c6d7-4218-90dc-6691eae563fb",
      "18ceeeaf-65ce-4747-8aaa-37c2429300bd",
      "f4b8b914-11a5-46c8-a367-fccfc156af83",
      "c3bad53c-fb84-4eda-8482-786c9dbc2276",
      "7e420d78-e63f-4a5d-bead-bc4f0e94ba3a",
      "88d2928d-84ed-45c9-ac53-01da9f8329fc",
      "e6d50c03-6f27-419e-88bc-82a7f63da55a",
      "30f112ad-14a4-48d2-98f2-049a593f284e",
      "26faaf7d-9cd0-4ab6-a3f8-350b62a8c6fc",
      "27be5516-4c7c-4551-bbce-63f3891b74eb",
      "eb3c20cb-1318-4dce-8c34-e646fe4897e1",
      "7d871f4b-ddb5-4473-b1ca-0b639a1af020",
      "3b86e144-b6a1-4586-bd58-803ed4e2a4c7",
      "42b4a65f-3086-483e-b2ee-bde995eae2f8",
      "07c5a4bd-9caa-41a1-85e5-9133861421ee",
      "f374c9d1-361f-498e-ac47-89bd43423ee6",
      "723fb9e3-2ee8-43ba-8454-accaf07b9f47",
      "7419a865-e0f2-4562-a78f-b3ef3a839a16",
      "fa7548f3-f760-49ee-871e-90544fc129cf",
      "fafead5a-7f1e-4fd7-9b30-e07331e11587",
      "3718fd91-e93e-4021-af70-524ba315acab",
      "f5d0c563-d68a-440e-a30f-fcdbfe56dea1",
      "62c5786d-6cf7-42e6-8011-18b1550b52db",
      "45dc3788-9b38-485d-bf1b-7ee6296596d8",
      "eb71351b-0f7c-4900-89b1-07bb9da6e9da",
      "bb2a9254-55b3-4fa6-91cd-d3da6808fd57",
      "97c627ab-9fbb-470d-ba9c-4aff4ae8e1b6",
      "5a90786f-0229-407f-b6a7-d3d30530b1d9",
      "f0ea875f-fd42-4245-881b-280d9c7ccbe0",
      "a9f94805-9f41-4fef-85a8-b969abcb37c4",
      "d910fbee-9a77-4ec4-8e68-d6d439c81d78",
      "966c704f-8f0e-4ed1-a457-4fa0cea545d2",
      "ebbcce82-17bd-4c90-a133-9195dd9f5a51",
      "f49ff69f-b56a-4d34-93a5-04364ed9bfa9",
      "5efd0041-eb1f-4cda-b09c-5c08a092b3fe",
      "f73a1e57-6c31-4c43-87c8-ad9969d4e7b0",
      "e190cdaa-c270-4159-b6e4-d400f505441c",
      "8e758f51-68e1-4f27-9114-b46cdd0cdf7e",
      -- トライアル設計レビュー情報
      "e5efe9cc-f1d3-417a-9252-d7dc9b93e268",
      "abbf9c85-ca03-4e5a-9a59-3ea53e732a82",
      "bc1121ee-7405-4b82-9154-ce0bcf911623",
      "253ec530-e512-4118-a40c-f0e646006838",
      "d45ae805-bc34-43c7-aa11-8171e5194612",
      "926834cd-b6e2-4afa-ae48-7539adcc4ce9",
      "b32f28ba-5363-42c7-bc21-2049dbc350b5",
      "79fba2cf-57a6-453d-abcf-febb9f2e0ea9",
      "b3d8a510-563c-4249-9655-608d33dbb4d0",
      "612258e0-67ea-4806-a997-89202d579a9e",
      "bdc0e3e4-9b84-4697-915b-80cb71838a74",
      "e5c01970-de1b-44b2-b9ab-7b38d5e570b8",
      "a68a1f51-292d-4e12-8f4f-20477879967b",
      "540bcfc4-122a-44fd-b9bd-c509e0dc81f6",
      "7636ca45-5fba-4ddd-b873-16008301daee"
  )
)
SELECT 
  tenant_id,
  original_id,
  drawing_id,
  page_number,
  REPLACE(file_path, "gs://zoolake-prod.appspot.com/", "") as original_gcs_blob_path,
  FORMAT(
    "%s.%s",
    drawing_id,
    "png"
  ) as original_local_path,  
FROM 
  drawing
INNER JOIN `esperanto-drawer-prod.dl_catalyst_alloydb.catalyst_drawing_png_image` USING(drawing_id)
"""


def query(query_str: str, project_id: str = "ai-lab-drawer-ml-dev") -> pd.DataFrame:
    bq_client = bigquery.Client()
    job_config = bigquery.QueryJobConfig(use_query_cache=True)

    df = bq_client.query(
        query_str,
        job_config=job_config,
        project=project_id,
    ).to_dataframe()
    return df


def download_blob(bucket: storage.Bucket, source_blob_name: str, destination_file_name: Path):
    """Download a blob from the bucket."""
    destination_file_name.parent.mkdir(parents=True, exist_ok=True)
    if destination_file_name.exists():
        return

    blob = bucket.blob(source_blob_name)
    if not blob.exists():
        logger.warning(f"Blob does not exist in GCS: {source_blob_name}")
        return

    blob.download_to_filename(destination_file_name)


def _download_blob(args):
    """Download blob using multiprocessing arguments"""
    download_blob(*args)


def download_images_from_gcs(
    data_dir: str | Path,
    blob_paths: list[str],
    local_paths: list[str],
    bucket_name: str = "drawer_drawing_images",
    n_worker: int = 4,
) -> None:
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    args = [
        (bucket, blob_path, Path(f"{data_dir}/{local_path}"))
        for blob_path, local_path in zip(blob_paths, local_paths, strict=False)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_worker) as executor:
        futures = [executor.submit(_download_blob, a) for a in args]
        for idx, _ in enumerate(concurrent.futures.as_completed(futures)):
            if (idx + 1) % 100 == 0:
                logger.info(f"Download {idx + 1:,} / {len(args):,} images from gcs ...")


@click.command()
@click.option(
    "--data-dir", required=True, type=click.Path(path_type=Path), help="Directory to save downloaded files"
)
@click.option(
    "--query-mode",
    required=True,
    help="Query mode",
    type=click.Choice(["original", "drawing"]),
)
@click.option("--bucket-name", default="drawer_drawing_images", help="GCS bucket name for downloading files")
@click.option("--project-id", default="ai-lab-drawer-ml-dev", help="BigQuery project ID")
@click.option("--n-worker", default=4, type=int, help="Number of parallel download workers")
def main(data_dir: Path, query_mode: str, bucket_name: str, project_id: str, n_worker: int):
    logger.info("Starting BigQuery data retrieval and GCS download process")

    # BigQuery query to get drawing image metadata
    query_str = QUERY_STRS[query_mode]

    logger.info("Executing BigQuery query")
    df = query(query_str, project_id=project_id)
    logger.info(f"Retrieved {len(df)} records from BigQuery")

    if df.empty:
        logger.warning("No data retrieved from BigQuery")
        return

    # Process data to create GCS blob paths and local paths
    logger.info("Processing data for GCS download")
    blob_paths = df["original_gcs_blob_path"].tolist()
    local_paths = df["original_local_path"].tolist()

    logger.info(f"Starting download of {len(blob_paths)} files from GCS")
    download_images_from_gcs(
        data_dir=data_dir,
        blob_paths=blob_paths,
        local_paths=local_paths,
        bucket_name=bucket_name,
        n_worker=n_worker,
    )

    df.to_csv(data_dir / "metadata.csv", index=False)
    logger.info("Download process completed successfully")


if __name__ == "__main__":
    main()
