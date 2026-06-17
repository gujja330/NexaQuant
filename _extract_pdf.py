import io
from pypdf import PdfReader
path = r"C:\Users\GPraveenKumar\.claude\projects\c--Users-GPraveenKumar-Downloads-marl\415c713e-e7d8-49ea-a339-481545da8e22\tool-results\webfetch-1781680734941-ap4ers.pdf"
r = PdfReader(path)
out = io.open(r"C:\Users\GPraveenKumar\Downloads\marl\_pdf_text.txt", "w", encoding="utf-8")
for i, p in enumerate(r.pages):
    out.write("==== PAGE %d ====\n" % (i + 1))
    out.write(p.extract_text() or "")
    out.write("\n")
out.close()
print("done")
