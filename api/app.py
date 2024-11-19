from flask import Flask, request, render_template, send_file, redirect, url_for
import os
import tempfile
import pandas as pd
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Function to sanitize UPC codes
def sanitize_upc(upc):
    try:
        if pd.isna(upc):
            return ''
        upc_str = str(int(float(upc)))
        upc_str = ''.join(filter(str.isdigit, upc_str))
        return upc_str
    except ValueError:
        return ''

# Function to pad UPC codes
def pad_upc(upc):
    if len(upc) < 12:
        return upc.zfill(12)
    elif 12 < len(upc) < 13:
        return upc.zfill(13)
    return upc

@app.route('/')
def upload_file():
    return render_template('upload.html')

@app.route('/generate', methods=['POST'])
def generate():
    try:
        # Check if a file was uploaded
        if 'file' not in request.files:
            return "Error: No file uploaded.", 400

        file = request.files['file']
        if file.filename == '':
            return "Error: No file selected.", 400

        # Save the uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Read and process the file
        try:
            df = pd.read_excel(file_path, sheet_name=0, skiprows=10)
            if "Unnamed: 13" not in df.columns:
                return "Error: 'Unnamed: 13' column not found in the uploaded file.", 400
            df = df[["Unnamed: 13"]].dropna()
            df.columns = ['UPC']
        except Exception as e:
            return f"Error processing file: {str(e)}", 500

        # Generate barcodes
        temp_dir = tempfile.mkdtemp()
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        images_per_row, images_per_col = 2, 3
        image_width, image_height, margin = 75, 50, 5

        for i, upc in enumerate(df['UPC'].apply(sanitize_upc).apply(pad_upc)):
            try:
                barcode_class = barcode.get_barcode_class('upca' if len(upc) == 12 else 'ean13')
                upc_barcode = barcode_class(upc, writer=ImageWriter())
                barcode_path = os.path.join(temp_dir, f"{upc}.png")
                upc_barcode.save(barcode_path)

                # Add barcode to PDF
                if i % (images_per_row * images_per_col) == 0:
                    pdf.add_page()
                row, col = divmod(i % (images_per_row * images_per_col), images_per_row)
                x, y = margin + col * (image_width + margin), margin + row * (image_height + margin)
                pdf.image(barcode_path, x, y, w=image_width, h=image_height)
            except Exception as e:
                return f"Error generating barcode for {upc}: {str(e)}", 500

        # Save the PDF
        pdf_path = os.path.join(temp_dir, "barcodes.pdf")
        pdf.output(pdf_path)
        return send_file(pdf_path, as_attachment=True, download_name="barcodes.pdf")

    except Exception as e:
        return f"Error: {str(e)}", 500
