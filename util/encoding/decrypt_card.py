"""
Credits:
akintos: https://gist.github.com/akintos/04e2494c62184d2d4384078b0511673b
timelic: https://github.com/timelic/master-duel-chinese-translation-switch
"""

from typing import List
import json
import zlib

from database.models import CardMetadataModel
from database.objects import session
from util.constants import APP_CONFIG


# 0. Definitions


def Decrypt(data: bytes, m_iCryptoKey):
    data = bytearray(data)
    try:
        for i in range(len(data)):
            v = i + m_iCryptoKey + 0x23D
            v *= m_iCryptoKey
            v ^= i % 7
            data[i] ^= v & 0xFF
        return zlib.decompress(data)
    except zlib.error:
        return bytearray()


def ReadByteData(filename):
    return (
        session.query(CardMetadataModel)
        .where(CardMetadataModel.name == filename)
        .first()
        .data
    )


def WriteDecByteData(filename, data):
    metadata = (
        session.query(CardMetadataModel)
        .where(CardMetadataModel.name == filename)
        .first()
    )
    metadata.data_decoded = data
    session.commit()


def CheckCryptoKey(filename, m_iCryptoKey):
    data = ReadByteData(filename)
    if Decrypt(data, m_iCryptoKey) == bytearray():
        return 0
    else:
        return 1


def FindCryptoKey(filename):
    m_iCryptoKey = -0x1
    data = ReadByteData(filename)
    dec_data = bytearray()
    while dec_data == bytearray():
        m_iCryptoKey = m_iCryptoKey + 1
        dec_data = Decrypt(data, m_iCryptoKey)
    APP_CONFIG.crypto_key = hex(m_iCryptoKey)
    session.commit()
    return m_iCryptoKey


def GetCryptoKey(filename):
    if APP_CONFIG.crypto_key:
        m_iCryptoKey = int(APP_CONFIG.crypto_key, 16)
    else:
        m_iCryptoKey = 0x0

    if CheckCryptoKey(filename, m_iCryptoKey) != 1:
        m_iCryptoKey = FindCryptoKey(filename)
    return m_iCryptoKey


# The start of Name and Desc is 0 and 4 respectively
def ProgressiveProcessing(CARD_Indx_filename, filename, start):

    # Read binary index
    indx_metadata = (
        session.query(CardMetadataModel)
        .where(CardMetadataModel.name == CARD_Indx_filename)
        .first()
    )
    hex_str_list = (
        "{:02X}".format(int(c)) for c in indx_metadata.data_decoded
    )  # Define variables to accept file contents
    dec_list = [int(s, 16) for s in hex_str_list]  # Convert hexadecimal to decimal

    # Get the index of Desc
    indx = []
    for i in range(start, len(dec_list), 8):
        tmp = []
        for j in range(4):
            tmp.append(dec_list[i + j])
        indx.append(tmp)

    def FourToOne(x: List[int]) -> int:
        res = 0
        for i in range(3, -1, -1):
            res *= 16 * 16
            res += x[i]
        return res

    indx = [FourToOne(i) for i in indx]
    indx = indx[1:]

    # Convert Decrypted CARD files to JSON files
    def Solve(data: bytes, desc_indx: List[int]):
        res = []
        for i in range(len(desc_indx) - 1):
            s = data[desc_indx[i] : desc_indx[i + 1]]
            s = s.decode("UTF-8", "ignore")
            while len(s) > 0 and s[-1] == "\u0000":
                s = s[:-1]
            res.append(s)
        return res

    # Read Desc file
    desc = (
        session.query(CardMetadataModel)
        .where(CardMetadataModel.name == filename)
        .first()
    )

    desc_json = Solve(desc.data_decoded, indx)

    desc.data_json = json.dumps(desc_json)
    session.commit()


def decrypt_desc_indx_name():

    # 1. Check if CARD_* files exist:

    CARD_Indx_filename = "card_indx.bytes"
    CARD_Name_filename = "card_name.bytes"
    CARD_Desc_filename = "card_desc.bytes"

    # 2. Get crypto key

    m_iCryptoKey = GetCryptoKey(CARD_Indx_filename)

    # 3. Decrypt card files from section 1

    for filename in [CARD_Indx_filename, CARD_Name_filename, CARD_Desc_filename]:
        data = ReadByteData(filename)
        data = Decrypt(data, m_iCryptoKey)
        WriteDecByteData(filename, data)

    # 4. Split CARD_Name + CARD_Desc

    ProgressiveProcessing(CARD_Indx_filename, CARD_Name_filename, 0)
    ProgressiveProcessing(CARD_Indx_filename, CARD_Desc_filename, 4)
