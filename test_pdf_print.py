import os
import sys
import win32print
import win32ui
import win32con
import pythoncom
import fitz  # PyMuPDF
from PIL import Image, ImageWin

def test_print_pdf(filepath: str, printer_name: str) -> None:
    pythoncom.CoInitialize()
    try:
        print(f"Opening printer: {printer_name}")
        hprinter = win32print.OpenPrinter(printer_name)
        try:
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)

            printer_dpi_x = hdc.GetDeviceCaps(win32con.LOGPIXELSX)
            printer_dpi_y = hdc.GetDeviceCaps(win32con.LOGPIXELSY)
            phys_width = hdc.GetDeviceCaps(win32con.PHYSICALWIDTH)
            phys_height = hdc.GetDeviceCaps(win32con.PHYSICALHEIGHT)

            print(f"Printer DPI: {printer_dpi_x}x{printer_dpi_y}")
            print(f"Physical Size: {phys_width}x{phys_height}")

            hdc.StartDoc(filepath)

            pdf_doc = fitz.open(filepath)
            for page_num in range(len(pdf_doc)):
                print(f"Printing page {page_num+1}...")
                hdc.StartPage()
                
                page = pdf_doc.load_page(page_num)
                
                # PyMuPDF default DPI is 72. Calculate zoom to match printer DPI.
                zoom_x = printer_dpi_x / 72.0
                zoom_y = printer_dpi_y / 72.0
                matrix = fitz.Matrix(zoom_x, zoom_y)
                
                # Render to pixmap
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Draw to DC
                dib = ImageWin.Dib(img)
                dib.draw(hdc.GetHandleOutput(), (0, 0, pix.width, pix.height))
                
                hdc.EndPage()
                
            pdf_doc.close()
            hdc.EndDoc()
            hdc.DeleteDC()
            print("Successfully spooled to printer.")
        finally:
            win32print.ClosePrinter(hprinter)
    finally:
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_pdf_print.py <pdf_path> <printer_name>")
        sys.exit(1)
    test_print_pdf(sys.argv[1], sys.argv[2])
