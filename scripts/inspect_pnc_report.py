"""Inspect a stored HTML report revision without modifying cloud data."""
import hashlib
import re
import argparse
from io import BytesIO
from pypdf import PdfReader

from databricks.sdk import WorkspaceClient
from vigie_databricks.pnc_extraction import _ReportText
from review_pnc_staging import query


def main():
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument("--company", choices=("DFY", "IFC", "TD"), default="DFY")
    args = args_parser.parse_args()
    client = WorkspaceClient(profile="jeplante")
    documents = query(client, f"SELECT to_json(struct(*)) FROM workspace.vigie.pnc_financial_documents WHERE company_id = '{args.company}'")
    for document in documents:
        response = client.files.download(document["raw_content_path"])
        content = response.contents.read()
        digest = hashlib.sha256(content).hexdigest()
        if digest != document["content_hash"]:
            raise ValueError("Stored report hash mismatch")
        if document["content_type"] == "application/pdf":
            print("SHA256", digest)
            for number, page in enumerate(PdfReader(BytesIO(content)).pages, 1):
                text = page.extract_text() or ""
                if "Insurance net income" in text:
                    print("PAGE", number, text)
            continue
        parser = _ReportText()
        parser.feed(content.decode("utf-8"))
        text = re.sub(r"\s+", " ", " ".join(parser.parts))
        print("SHA256", digest)
        phrases = (("reports Q2", "Combined ratio of", "Consolidated highlights") if args.company == "IFC"
                   else ("Consolidated Results", "Net Income and Operating Net Income", "Operating ROE was"))
        for phrase in phrases:
            position = text.lower().find(phrase.lower())
            print(phrase, position, text[position:position + 2200] if position >= 0 else "NOT FOUND")


if __name__ == "__main__":
    main()
