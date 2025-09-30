from PyPDF2 import PdfFileMerger
import os
from pathlib import Path


def pdfFileAppend(inputPath, outputPath, fileName):
    merger = PdfFileMerger()
    fileList = os.listdir(Path(inputPath))
    fileList.pop()
    fileList.sort()
    print(fileList)
    for i in range(len(fileList)):
        file = str(i + 1) + ".pdf"
        merger.append(inputPath + file)
    merger.write(outputPath + fileName)
    merger.close()
