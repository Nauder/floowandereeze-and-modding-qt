"""
Credit:
- timelic from NexusMods: https://forums.nexusmods.com/index.php?/user/145588218-timelic

Original source:
https://bitbucket.org/timel/master-duel-chinese-translation-patch/src/master/%E5%8D%A1%E7%89%87CARD/c_CARD%E5%8E%8B%E7%BC%A9.py
"""

from ast import literal_eval
from typing import List
import zlib

from database.models import CardMetadataModel
from database.objects import session
from util.constants import APP_CONFIG


CARD_Indx_filename = "card_indx.bytes"
CARD_Name_filename = "card_name.bytes"
CARD_Desc_filename = "card_desc.bytes"


def getStringLen(s: str):
    return len(s.encode("utf-8"))


def intTo4Hex(num: int) -> List[int]:
    res = []
    for _ in range(4):
        res.append(num % 256)
        num //= 256
    return res


def Decrypt(filename):
    metadata: CardMetadataModel = (
        session.query(CardMetadataModel)
        .filter(CardMetadataModel.name == filename)
        .first()
    )
    m_iCryptoKey = int(APP_CONFIG.crypto_key, 16)

    data = bytearray(metadata.data)

    for i in range(len(data)):
        v = i + m_iCryptoKey + 0x23D
        v *= m_iCryptoKey
        v ^= i % 7
        data[i] ^= v & 0xFF

    metadata.data_decoded = zlib.decompress(data)

    session.commit()


def CheckCryptoKey():
    try:
        Decrypt(CARD_Indx_filename)
        return 1
    except zlib.error:
        return 0


def encrypt(b: bytes):
    m_iCryptoKey = int(APP_CONFIG.crypto_key, 16)
    data = bytearray(zlib.compress(b))

    for i in range(len(data)):
        v = i + m_iCryptoKey + 0x23D
        v *= m_iCryptoKey
        v ^= i % 7
        data[i] ^= v & 0xFF

    return data


def merge_data():

    CARD_Name_json: list = literal_eval(
        session.query(CardMetadataModel)
        .where(CardMetadataModel.name == "card_name.bytes")
        .first()
        .data_json
    )
    CARD_Desc_json: list = literal_eval(
        session.query(CardMetadataModel)
        .where(CardMetadataModel.name == "card_desc.bytes")
        .first()
        .data_json
    )

    # 3. Merge JSON files

    merge_string = {"name": "\u0000" * 8, "desc": "\u0000" * 8}

    name_indx = [0]
    desc_indx = [0]

    for i in range(
        len(CARD_Name_json)
    ):  # Here because of a strange bug in English desc is one less than name
        name = CARD_Name_json[i]
        desc = CARD_Desc_json[i]

        def helper(
            sentence: str, indx: List[int], name_or_desc: str, merge_string: dict
        ):
            length = getStringLen(sentence)
            if i == 0:
                length += 8
            space_len = 4 - length % 4  # It means getting the remainder
            indx.append(indx[-1] + length + space_len)  # Record indx
            if name_or_desc == "name":
                merge_string["name"] += sentence + "\u0000" * space_len
            else:
                merge_string["desc"] += sentence + "\u0000" * space_len

        helper(name, name_indx, "name", merge_string)
        helper(desc, desc_indx, "desc", merge_string)

    # 4. Calculate CARD index

    # Compression
    # Can't compress. Compression is a problem.

    name_indx = [4, 8] + name_indx[1:]
    desc_indx = [4, 8] + desc_indx[1:]

    card_indx = []
    for i in range(len(name_indx)):
        card_indx.append(name_indx[i])
        card_indx.append(desc_indx[i])

    card_indx_merge = []
    for item in card_indx:
        card_indx_merge.extend(intTo4Hex(item))

    return (
        encrypt(bytes(merge_string["name"], encoding="utf-8")),
        encrypt(bytes(merge_string["desc"], encoding="utf-8")),
        encrypt(bytes(card_indx_merge)),
    )
