#!/usr/bin/env python3
"""Generate synthetic, signed NF-e XML samples for the office pipeline."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from lxml import etree


ROOT = Path(__file__).resolve().parent / "nfe"
NS = "http://www.portalfiscal.inf.br/nfe"
DS = "http://www.w3.org/2000/09/xmldsig#"

CLIENT_CNPJS = {
    "Mercado Dois Irmãos Ltda.": "14289630000132",
    "Clínica Viver Bem Ltda.": "28750411000113",
    "Oficina Horizonte Ltda.": "06741229000163",
    "Ateliê Maré Alta ME": "41083526000160",
    "Ponto Norte Logística Ltda.": "09562148000194",
    "Casa do Cacau Comércio Ltda.": "32117685000147",
    "Verdejar Paisagismo ME": "17625900000127",
    "Nuvem Criativa Serviços Ltda.": "23300194000146",
}

CASES = [
    {"sample_number":"000.008.491","date":"2026-10-19","amount":1842.70,"movement":"Entrada","issuer":"Distribuidora Baía Norte Ltda.","recipient":"Mercado Dois Irmãos Ltda.","client":"Mercado Dois Irmãos Ltda.","cfop":"1102","product":"Biscoitos sortidos de demonstração","ncm":"19053100","expected":"not_applicable"},
    {"sample_number":"000.003.017","date":"2026-10-19","amount":2760.00,"movement":"Saída","issuer":"Clínica Viver Bem Ltda.","recipient":"Laboratório São Lucas Ltda.","client":"Clínica Viver Bem Ltda.","cfop":"5102","product":"Kit de reagentes de demonstração","ncm":"38221900","expected":"needs_parameters"},
    {"sample_number":"000.014.250","date":"2026-10-18","amount":935.45,"movement":"Saída","issuer":"Casa do Cacau Comércio Ltda.","recipient":"Empório Sabor da Bahia Ltda.","client":"Casa do Cacau Comércio Ltda.","cfop":"5102","product":"Chocolate artesanal de demonstração","ncm":"18063210","expected":"calculated"},
    {"sample_number":"000.006.819","date":"2026-10-18","amount":4200.00,"movement":"Saída","issuer":"Nuvem Criativa Serviços Ltda.","recipient":"Instituto Mar Aberto Ltda.","client":"Nuvem Criativa Serviços Ltda.","cfop":"5102","product":"Equipamento de informática de demonstração","ncm":"84713012","expected":"needs_parameters"},
    {"sample_number":"000.002.884","date":"2026-10-17","amount":1520.00,"movement":"Saída","issuer":"Verdejar Paisagismo ME","recipient":"Condomínio Jardim das Dunas Ltda.","client":"Verdejar Paisagismo ME","cfop":"5102","product":"Mudas ornamentais de demonstração","ncm":"06029029","expected":"calculated"},
    {"sample_number":"000.001.374","date":"2026-10-17","amount":3890.00,"movement":"Saída","issuer":"Oficina Horizonte Ltda.","recipient":"Rota Sul Transportes Ltda.","client":"Oficina Horizonte Ltda.","cfop":"5102","product":"Peças automotivas de demonstração","ncm":"87089990","expected":"calculated"},
    {"sample_number":"000.016.211","date":"2026-10-16","amount":6432.18,"movement":"Entrada","issuer":"Atacado Costa Verde Ltda.","recipient":"Mercado Dois Irmãos Ltda.","client":"Mercado Dois Irmãos Ltda.","cfop":"1102","product":"Mercadorias para revenda de demonstração","ncm":"21069090","expected":"not_applicable"},
    {"sample_number":"000.004.422","date":"2026-10-16","amount":1765.30,"movement":"Entrada","issuer":"Farma Bahia Distribuição Ltda.","recipient":"Clínica Viver Bem Ltda.","client":"Clínica Viver Bem Ltda.","cfop":"1102","product":"Medicamento de demonstração","ncm":"30049099","expected":"not_applicable"},
    {"sample_number":"000.000.976","date":"2026-10-15","amount":12500.00,"movement":"Saída","issuer":"Ponto Norte Logística Ltda.","recipient":"Norte Peças e Motores Ltda.","client":"Ponto Norte Logística Ltda.","cfop":"5102","product":"Equipamento logístico de demonstração","ncm":"84279000","expected":"not_applicable"},
    {"sample_number":"000.001.180","date":"2026-10-15","amount":428.90,"movement":"Saída","issuer":"Casa do Cacau Comércio Ltda.","recipient":"Padaria Pão da Vila Ltda.","client":"Casa do Cacau Comércio Ltda.","cfop":"5102","product":"Chocolate artesanal de demonstração","ncm":"18063210","expected":"calculated"},
    {"sample_number":"000.002.032","date":"2026-10-14","amount":2100.00,"movement":"Saída","issuer":"Mercado Dois Irmãos Ltda.","recipient":"Restaurante Varanda do Mar Ltda.","client":"Mercado Dois Irmãos Ltda.","cfop":"5102","product":"Alimentos para revenda de demonstração","ncm":"21069090","expected":"calculated"},
    {"sample_number":"000.000.857","date":"2026-10-13","amount":6100.00,"movement":"Saída","issuer":"Clínica Viver Bem Ltda.","recipient":"Plano Vida Mais S.A.","client":"Clínica Viver Bem Ltda.","cfop":"5102","product":"Material de saúde de demonstração","ncm":"30059090","expected":"needs_parameters"},
]


def cnpj_check_digit(base: str, weights: list[int]) -> str:
    remainder = sum(int(digit) * weight for digit, weight in zip(base, weights)) % 11
    return "0" if remainder < 2 else str(11 - remainder)


def valid_cnpj(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 14:
        return False
    first = cnpj_check_digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = cnpj_check_digit(digits[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digits[-2:] == first + second


def cnpj_for_party(name: str) -> str:
    if name in CLIENT_CNPJS:
        return CLIENT_CNPJS[name]
    prefix = str(int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:12], 16) % 100_000_000).zfill(8) + "0001"
    first = cnpj_check_digit(prefix, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return prefix + first + cnpj_check_digit(prefix + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])


def access_key(issuer_cnpj: str, issue_date: str, number: int) -> str:
    date = datetime.strptime(issue_date, "%Y-%m-%d")
    c_nf = f"{(number * 7919) % 100_000_000:08d}"
    base = f"29{date:%y%m}{issuer_cnpj}55{1:03d}{number:09d}1{c_nf}"
    total = sum(int(digit) * (2 + (len(base) - 1 - i) % 8) for i, digit in enumerate(base))
    remainder = total % 11
    digit = "0" if remainder in (0, 1) else str(11 - remainder)
    return base + digit


def add(parent: etree._Element, name: str, value: str | int) -> etree._Element:
    node = etree.SubElement(parent, f"{{{NS}}}{name}")
    node.text = str(value)
    return node


def decimal(value: float) -> str:
    return f"{value:.2f}"


def build_signature(root: etree._Element, inf_nfe: etree._Element, nfe_key: str) -> None:
    # Ephemeral self-signed key: structurally and cryptographically testable,
    # deliberately not an ICP-Brasil issuer certificate.
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "METIS TESTE FISCAL - SEM VALIDADE")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(private_key, hashes.SHA256())
    )
    q = lambda name: f"{{{DS}}}{name}"
    signature = etree.SubElement(root, q("Signature"), nsmap={"ds": DS})
    signed_info = etree.SubElement(signature, q("SignedInfo"))
    etree.SubElement(signed_info, q("CanonicalizationMethod"), Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
    etree.SubElement(signed_info, q("SignatureMethod"), Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1")
    reference = etree.SubElement(signed_info, q("Reference"), URI=f"#NFe{nfe_key}")
    transforms = etree.SubElement(reference, q("Transforms"))
    etree.SubElement(transforms, q("Transform"), Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
    etree.SubElement(transforms, q("Transform"), Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
    etree.SubElement(reference, q("DigestMethod"), Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
    digest = hashlib.sha1(etree.tostring(inf_nfe, method="c14n", exclusive=False, with_comments=False)).digest()
    etree.SubElement(reference, q("DigestValue")).text = base64.b64encode(digest).decode("ascii")
    signature_value = etree.SubElement(signature, q("SignatureValue"))
    key_info = etree.SubElement(signature, q("KeyInfo"))
    x509_data = etree.SubElement(key_info, q("X509Data"))
    etree.SubElement(x509_data, q("X509Certificate")).text = base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode("ascii")
    signed_info_c14n = etree.tostring(signed_info, method="c14n", exclusive=False, with_comments=False)
    signature_value.text = base64.b64encode(private_key.sign(signed_info_c14n, padding.PKCS1v15(), hashes.SHA1())).decode("ascii")


def build_xml(case: dict) -> tuple[bytes, str, str, str]:
    issuer_cnpj = cnpj_for_party(case["issuer"])
    recipient_cnpj = cnpj_for_party(case["recipient"])
    number = int(case["sample_number"].replace(".", ""))
    key = access_key(issuer_cnpj, case["date"], number)
    root = etree.Element(f"{{{NS}}}NFe", nsmap={None: NS})
    inf = etree.SubElement(root, f"{{{NS}}}infNFe", Id=f"NFe{key}", versao="4.00")
    ide = etree.SubElement(inf, f"{{{NS}}}ide")
    for tag, value in [
        ("cUF", "29"), ("cNF", key[35:43]), ("natOp", "Venda de mercadoria de demonstração"),
        ("mod", "55"), ("serie", "1"), ("nNF", str(number)), ("dhEmi", f"{case['date']}T12:00:00-03:00"),
        ("tpNF", "0" if case["movement"] == "Entrada" else "1"), ("idDest", "1"), ("cMunFG", "2927408"),
        ("tpImp", "1"), ("tpEmis", "1"), ("cDV", key[-1]), ("tpAmb", "2"), ("finNFe", "1"),
        ("indFinal", "1"), ("indPres", "1"), ("procEmi", "0"), ("verProc", "Metis Teste 1.0"),
    ]:
        add(ide, tag, value)

    issuer = etree.SubElement(inf, f"{{{NS}}}emit")
    add(issuer, "CNPJ", issuer_cnpj)
    add(issuer, "xNome", case["issuer"])
    issuer_address = etree.SubElement(issuer, f"{{{NS}}}enderEmit")
    for tag, value in [("xLgr", "Rua Exemplo"), ("nro", "100"), ("xBairro", "Centro"), ("cMun", "2927408"), ("xMun", "Salvador"), ("UF", "BA"), ("CEP", "40000000"), ("cPais", "1058"), ("xPais", "Brasil"), ("fone", "71999990000")]:
        add(issuer_address, tag, value)
    add(issuer, "IE", "123456789")
    add(issuer, "CRT", "3" if case["issuer"] == "Ponto Norte Logística Ltda." else "1")

    recipient = etree.SubElement(inf, f"{{{NS}}}dest")
    add(recipient, "CNPJ", recipient_cnpj)
    add(recipient, "xNome", case["recipient"])
    recipient_address = etree.SubElement(recipient, f"{{{NS}}}enderDest")
    for tag, value in [("xLgr", "Avenida Teste"), ("nro", "20"), ("xBairro", "Centro"), ("cMun", "2927408"), ("xMun", "Salvador"), ("UF", "BA"), ("CEP", "40000000"), ("cPais", "1058"), ("xPais", "Brasil")]:
        add(recipient_address, tag, value)
    add(recipient, "indIEDest", "9")

    amount = decimal(case["amount"])
    detail = etree.SubElement(inf, f"{{{NS}}}det", nItem="1")
    product = etree.SubElement(detail, f"{{{NS}}}prod")
    for tag, value in [
        ("cProd", f"DEMO-{number:06d}"), ("cEAN", "SEM GTIN"), ("xProd", case["product"]), ("NCM", case["ncm"]),
        ("CFOP", case["cfop"]), ("uCom", "UN"), ("qCom", "1.0000"), ("vUnCom", amount), ("vProd", amount),
        ("cEANTrib", "SEM GTIN"), ("uTrib", "UN"), ("qTrib", "1.0000"), ("vUnTrib", amount), ("indTot", "1"),
    ]:
        add(product, tag, value)
    taxes = etree.SubElement(detail, f"{{{NS}}}imposto")
    icms = etree.SubElement(taxes, f"{{{NS}}}ICMS")
    if case["issuer"] == "Ponto Norte Logística Ltda.":
        branch = etree.SubElement(icms, f"{{{NS}}}ICMS40")
        add(branch, "orig", "0")
        add(branch, "CST", "40")
    else:
        branch = etree.SubElement(icms, f"{{{NS}}}ICMSSN102")
        add(branch, "orig", "0")
        add(branch, "CSOSN", "102")
    pis = etree.SubElement(taxes, f"{{{NS}}}PIS")
    pis_other = etree.SubElement(pis, f"{{{NS}}}PISOutr")
    for tag, value in [("CST", "49"), ("vBC", "0.00"), ("pPIS", "0.0000"), ("vPIS", "0.00")]:
        add(pis_other, tag, value)
    cofins = etree.SubElement(taxes, f"{{{NS}}}COFINS")
    cofins_other = etree.SubElement(cofins, f"{{{NS}}}COFINSOutr")
    for tag, value in [("CST", "49"), ("vBC", "0.00"), ("pCOFINS", "0.0000"), ("vCOFINS", "0.00")]:
        add(cofins_other, tag, value)

    total = etree.SubElement(inf, f"{{{NS}}}total")
    icms_total = etree.SubElement(total, f"{{{NS}}}ICMSTot")
    for tag, value in [
        ("vBC", "0.00"), ("vICMS", "0.00"), ("vICMSDeson", "0.00"), ("vFCP", "0.00"), ("vBCST", "0.00"),
        ("vST", "0.00"), ("vFCPST", "0.00"), ("vFCPSTRet", "0.00"), ("vProd", amount), ("vFrete", "0.00"),
        ("vSeg", "0.00"), ("vDesc", "0.00"), ("vII", "0.00"), ("vIPI", "0.00"), ("vIPIDevol", "0.00"),
        ("vPIS", "0.00"), ("vCOFINS", "0.00"), ("vOutro", "0.00"), ("vNF", amount), ("vTotTrib", "0.00"),
    ]:
        add(icms_total, tag, value)
    transport = etree.SubElement(inf, f"{{{NS}}}transp")
    add(transport, "modFrete", "9")
    payment = etree.SubElement(inf, f"{{{NS}}}pag")
    payment_detail = etree.SubElement(payment, f"{{{NS}}}detPag")
    add(payment_detail, "indPag", "0")
    add(payment_detail, "tPag", "99")
    add(payment_detail, "vPag", amount)
    additional = etree.SubElement(inf, f"{{{NS}}}infAdic")
    add(additional, "infCpl", "XML FICTÍCIO ASSINADO COM CERTIFICADO DE TESTE. NÃO TRANSMITIR; SEM AUTORIZAÇÃO SEFAZ.")
    build_signature(root, inf, key)
    # Pretty-printing would add whitespace text nodes inside infNFe after its
    # digest is calculated, which invalidates the enveloped XMLDSig.
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=False)
    return xml, key, issuer_cnpj, recipient_cnpj


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    output = []
    for case in CASES:
        number = case["sample_number"].replace(".", "")
        filename = f"DEMO-NFE-{number}.xml"
        xml, key, issuer_cnpj, recipient_cnpj = build_xml(case)
        (ROOT / filename).write_bytes(xml)
        output.append({
            **case,
            "filename": filename,
            "access_key": key,
            "issuer_cnpj": issuer_cnpj,
            "recipient_cnpj": recipient_cnpj,
            "client_cnpj": cnpj_for_party(case["client"]),
            "competence": case["date"][:7],
            "synthetic": True,
            "authorized_by_sefaz": False,
        })
    (ROOT / "manifest.json").write_text(json.dumps({
        "schema": "metis.demo-nfe-fixtures.v1",
        "xsd_package": "PL_010f_v1.04",
        "test_only": True,
        "fixtures": output,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(output)} schema-targeted synthetic NF-e XML files in {ROOT}")


if __name__ == "__main__":
    main()
