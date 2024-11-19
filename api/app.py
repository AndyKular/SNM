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
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir() or "/tmp"

# Function to sanitize UPC codes, handling NaN values and non-numeric data
def sanitize_upc(upc):
    try:
        if pd.isna(upc):
            return ''
        upc_str = str(int(float(upc)))
        upc_str = ''.join(filter(str.isdigit, upc_str))
        return upc_str
    except ValueError:
        return ''

# Function to pad UPC codes to 12 or 13 digits
def pad_upc(upc):
    if len(upc) < 12:
        upc = upc.zfill(12)
    elif 12 < len(upc) < 13:
        upc = upc.zfill(13)
    return upc

# Route for the file upload form
@app.route('/')
def upload_file():
    error = request.args.get('error')
    return render_template('upload.html', error=error)

# Route to handle file upload and barcode generation
@app.route('/generate', methods=['POST'])
def generate():
    if 'file' not in request.files:
        return redirect(url_for('upload_file', error="Error: No file uploaded."))

    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('upload_file', error="Error: Empty file uploaded."))

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # Save the uploaded file
    try:
        file.save(file_path)
        print(f"File saved at: {file_path}")
    except Exception as e:
        return redirect(url_for('upload_file', error=f"Error saving file: {e}"))

    # Try to read the file and check if the necessary column exists
    try:
        df = pd.read_excel(file_path, sheet_name=0, skiprows=10)
        if "Unnamed: 13" not in df.columns:
            return redirect(url_for('upload_file', error="'Unnamed: 13' column not found in the uploaded file."))
        df = df[["Unnamed: 13"]]  # Select only the needed column
        df.columns = ['UPC']
    except Exception as e:
        return redirect(url_for('upload_file', error=f"Error processing file: {e}"))

    # Process UPC codes
    df['UPC'] = df['UPC'].apply(sanitize_upc)
    upc_codes = df['UPC'].apply(pad_upc)
    upc_codes = upc_codes[upc_codes != '000000000000']

    temp_dir = tempfile.mkdtemp()
    generated_files = []

    # Barcode generation
    for upc in upc_codes:
        if upc:
            try:
                barcode_class = barcode.get_barcode_class('upca' if len(upc) == 12 else 'ean13')
                upc_barcode = barcode_class(upc, writer=ImageWriter())
                filename = os.path.join(temp_dir, f"{upc}.png")
                upc_barcode.save(filename.split('.png')[0])
                barcode_image = Image.open(filename)
                final_image = Image.new("RGB", (barcode_image.width, barcode_image.height + 30), "white")
                final_image.paste(barcode_image, (0, 0))

                draw = ImageDraw.Draw(final_image)
                font = ImageFont.load_default()
                text_position = ((barcode_image.width - draw.textlength(upc, font=font)) // 2, barcode_image.height)
                draw.text(text_position, upc, fill="black", font=font)

                final_filename = os.path.join(temp_dir, f"custom_{upc}.png")
                final_image.save(final_filename)
                generated_files.append(final_filename)
            except Exception as e:
                return redirect(url_for('upload_file', error=f"Error generating barcode for {upc}: {e}"))

    # Create a PDF from the generated barcode images
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        images_per_row, images_per_col = 2, 3
        image_width, image_height, margin = 75, 50, 5  # Adjust dimensions if needed

        for i, image_file in enumerate(generated_files):
            # Validate image file existence
            if not os.path.exists(image_file):
                print(f"Warning: Missing file {image_file}")
                continue

            if i % (images_per_row * images_per_col) == 0:
                pdf.add_page()
            row, col = divmod(i % (images_per_row * images_per_col), images_per_row)
            x, y = margin + col * (image_width + margin), margin + row * (image_height + margin)

            # Add image to PDF
            try:
                pdf.image(image_file, x, y, w=image_width, h=image_height)
            except Exception as e:
                print(f"Error adding image {image_file}: {e}")
                continue

        pdf_output_path = os.path.join(app.config['UPLOAD_FOLDER'], "barcodes.pdf")
        pdf.output(pdf_output_path)
        print(f"PDF saved at: {pdf_output_path}")  # Debugging statement
    except Exception as e:
        print(f"Error creating PDF: {e}")  # Debugging statement
        return redirect(url_for('upload_file', error=f"Error creating PDF: {e}"))

    # Clean up uploaded and temporary files
    try:
        os.remove(file_path)
        for f in generated_files:
            os.remove(f)
    except Exception as e:
        print(f"Error cleaning up files: {e}")

    # Automatically send the PDF for download
    try:
        return send_file(pdf_output_path, as_attachment=True, download_name="barcodes.pdf")
    except Exception as e:
        return redirect(url_for('upload_file', error=f"Error sending PDF file: {e}"))

# No need for app.run() as Vercel manages the server
