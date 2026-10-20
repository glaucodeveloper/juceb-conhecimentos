#!/usr/bin/env python3
"""Validate fixture XMLs against an official NF-e XSD and their test signatures."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509.oid import NameOID
from lxml import etree


ROOT = Path(__file__).resolve().parent / "nfe"
NS = "http://www.portalfiscal.inf.br/nfe"
DS = "http://www.w3.org/2000/09/xmldsig#"


def text(node: etree._Element | None, name: str) -> str:
    found = node.find(f"{{{NS}}}{name}") if node is not None else None
    return found.text.strip() if found is not None and found.text else ""


def check_digit(base: str) -> str:
    total = sum(int(digit) * (2 + (len(base) - 1 - i) % 8) for i, digit in enumerate(base))
    remainder = total % 11
    return "0" if remainder in (0, 1) else str(11 - remainder)


def validate_signature(root: etree._Element, inf: etree._Element, key: str) -> None:
    signature = root.find(f"{{{DS}}}Signature")
    if signature is None:
        raise ValueError("Signature XMLDSig ausente")
    signed_info = signature.find(f"{{{DS}}}SignedInfo")
    reference = signed_info.find(f"{{{DS}}}Reference") if signed_info is not None else None
    if reference is None or reference.get("URI") != f"#NFe{key}":
        raise ValueError("Reference XMLDSig não aponta para infNFe@Id")
    expected_digest = base64.b64encode(hashlib.sha1(etree.tostring(inf, method="c14n", exclusive=False, with_comments=False)).digest()).decode("ascii")
    actual_digest = reference.findtext(f"{{{DS}}}DigestValue", default="")
    if actual_digest != expected_digest:
        raise ValueError("Digest XMLDSig não confere com infNFe")
    certificate_text = signature.findtext(f".//{{{DS}}}X509Certificate", default="")
    certificate = x509.load_der_x509_certificate(base64.b64decode(certificate_text))
    if certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value != "METIS TESTE FISCAL - SEM VALIDADE":
        raise ValueError("O certificado do XML não está marcado como certificado sintético")
    signature_value = base64.b64decode(signature.findtext(f"{{{DS}}}SignatureValue", default=""))
    signed_info_c14n = etree.tostring(signed_info, method="c14n", exclusive=False, with_comments=False)
    try:
        certificate.public_key().verify(signature_value, signed_info_c14n, padding.PKCS1v15(), hashes.SHA1())
    except InvalidSignature as error:
        raise ValueError("Assinatura XMLDSig não confere") from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, type=Path, help="Caminho para o nfe_v4.00.xsd do pacote oficial")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    schema = etree.XMLSchema(etree.parse(str(args.schema)))
    passed = 0
    for fixture in manifest["fixtures"]:
        path = ROOT / fixture["filename"]
        doc = etree.parse(str(path), etree.XMLParser(resolve_entities=False, no_network=True))
        schema.assertValid(doc)
        root = doc.getroot()
        inf = root.find(f"{{{NS}}}infNFe")
        if inf is None:
            raise SystemExit(f"{path.name}: infNFe ausente")
        key = inf.get("Id", "").removeprefix("NFe")
        if len(key) != 44 or check_digit(key[:43]) != key[-1] or key != fixture["access_key"]:
            raise SystemExit(f"{path.name}: chave de acesso inválida ou divergente")
        for role in ("issuer_cnpj", "recipient_cnpj"):
            cnpj = fixture[role]
            if len(cnpj) != 14:
                raise SystemExit(f"{path.name}: CNPJ de teste deve conter 14 dígitos")
        validate_signature(root, inf, key)
        value = text(inf.find(f"{{{NS}}}total/{{{NS}}}ICMSTot"), "vNF")
        if round(float(value), 2) != round(float(fixture["amount"]), 2):
            raise SystemExit(f"{path.name}: vNF difere do manifesto")
        passed += 1
    print(f"OK: {passed} XMLs validados pelo XSD {manifest['xsd_package']} e assinatura XMLDSig de teste.")
    print("Limite: assinatura/certificado de demonstração não autoriza NF-e na SEFAZ.")


if __name__ == "__main__":
    main()
