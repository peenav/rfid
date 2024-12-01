from flask import Flask, jsonify, request, send_from_directory, send_file
import mysql.connector
from PIL import Image, ImageDraw, ImageFont
import io
from datetime import datetime, timedelta

app = Flask(__name__)

# Database connection setup
db = mysql.connector.connect(
    host="localhost",
    user="root",  # Your MySQL username
    password="",  # Your MySQL password (leave empty)
    database="rfid_payment_system"
)

# Route to serve the cashier interface
@app.route('/')
def cashier_interface():
    return send_from_directory('', 'index.html')

# Test route to ensure server is working
@app.route('/test', methods=['GET'])
def home():
    return "RFID Payment System Server is Running!"

# Route to get only active items
@app.route('/items', methods=['GET'])
def get_items():
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items WHERE is_active = TRUE")  # Only fetch active items
    items = cursor.fetchall()
    cursor.close()
    return jsonify(items)

# Route to add a new item
@app.route('/items', methods=['POST'])
def add_item():
    data = request.get_json()
    item_name = data['item_name']
    price = data['price']
    cursor = db.cursor()
    cursor.execute("INSERT INTO items (item_name, price) VALUES (%s, %s)", (item_name, price))
    db.commit()
    cursor.close()
    return jsonify({"message": "Item added successfully"}), 201

# Route to edit an existing item
@app.route('/items/<int:item_id>', methods=['PUT'])
def edit_item(item_id):
    data = request.get_json()
    item_name = data['item_name']
    price = data['price']
    cursor = db.cursor()
    cursor.execute("UPDATE items SET item_name = %s, price = %s WHERE item_id = %s", (item_name, price, item_id))
    db.commit()
    cursor.close()
    return jsonify({"message": "Item updated successfully"}), 200

# Route to "delete" an item by marking it as inactive
@app.route('/items/delete', methods=['DELETE'])
def delete_item_by_name():
    data = request.get_json()
    item_name = data['item_name']

    cursor = db.cursor()
    cursor.execute("SELECT * FROM items WHERE item_name = %s AND is_active = TRUE", (item_name,))
    item = cursor.fetchone()

    if item:
        cursor.execute("UPDATE items SET is_active = FALSE WHERE item_name = %s", (item_name,))
        db.commit()
        cursor.close()
        return jsonify({"message": f"Item '{item_name}' marked as inactive"}), 200
    else:
        cursor.close()
        return jsonify({"message": f"Item '{item_name}' not found or already inactive"}), 404






# Route to get student balance
@app.route('/student/<rfid>', methods=['GET'])
def get_student_balance(rfid):
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT student_id, name, balance FROM students WHERE rfid_number = %s", (rfid,))
    student = cursor.fetchone()
    cursor.close()
    if student:
        return jsonify(student)
    else:
        return jsonify({"error": "Student not found"}), 404

@app.route('/checkout', methods=['POST'])
def checkout():
    data = request.get_json()
    rfid = data['rfid']
    item_ids = data['items']

    # Calculate total cost of selected items
    cursor = db.cursor()
    cursor.execute("SELECT price FROM items WHERE item_id IN (%s)" % ','.join(['%s'] * len(item_ids)), item_ids)
    prices = cursor.fetchall()
    total_cost = sum(price[0] for price in prices)

    # Check the student's balance
    cursor.execute("SELECT student_id, balance, name FROM students WHERE rfid_number = %s", (rfid,))
    student = cursor.fetchone()
    if student:
        student_id = student[0]
        current_balance = student[1]
        student_name = student[2]
        if current_balance >= total_cost:
            # Deduct the total from the student's balance
            new_balance = current_balance - total_cost
            cursor.execute("UPDATE students SET balance = %s WHERE rfid_number = %s", (new_balance, rfid))

            # Insert transaction records for each item
            for item_id in item_ids:
                cursor.execute("INSERT INTO transactions (student_id, item_id, amount) VALUES (%s, %s, %s)",
                               (student_id, item_id, total_cost / len(item_ids)))  # Split the total cost among items

            db.commit()
            cursor.close()

            # Generate receipt image
            receipt_image_path = create_receipt(student_name, item_ids, total_cost)
            return jsonify({"message": "Payment successful!", "new_balance": new_balance, "receipt_image": receipt_image_path}), 200
        else:
            cursor.close()
            return jsonify({"error": "Insufficient balance"}), 400
    else:
        cursor.close()
        return jsonify({"error": "Student not found"}), 404

def create_receipt(student_name, item_ids, total_cost):
    # Create a blank image with white background
    img = Image.new('RGB', (400, 300), color='white')
    d = ImageDraw.Draw(img)

    # Add title
    title_font = ImageFont.load_default()
    d.text((10, 10), "INDIAN LANGUAGE SCHOOL CANTEEN", fill=(0, 0, 0), font=title_font)

    # Add student information
    d.text((10, 50), f"Student Name: {student_name}", fill=(0, 0, 0), font=title_font)

    # Add item information
    d.text((10, 80), "Items Purchased:", fill=(0, 0, 0), font=title_font)
    y_position = 100
    for item_id in item_ids:
        d.text((10, y_position), f"Item ID: {item_id}", fill=(0, 0, 0), font=title_font)
        y_position += 20

    # Add total cost
    d.text((10, y_position), f"Total Cost: ₹{total_cost:.2f}", fill=(0, 0, 0), font=title_font)

    # Save image to a BytesIO object
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    # Save image to file
    image_path = f'receipt_{int(datetime.now().timestamp())}.png'
    img.save(image_path)

    return image_path

@app.route('/download_receipt/<filename>', methods=['GET'])
def download_receipt(filename):
    return send_file(filename, as_attachment=True)

@app.route('/transactions/today', methods=['GET'])
def get_today_transactions():
    cursor = db.cursor(dictionary=True)
    
    # Get today's date in 'YYYY-MM-DD' format
    today = datetime.now().strftime('%Y-%m-%d')  # String format 'YYYY-MM-DD'
    
    # Modify the SQL query to filter transactions based on the current date
    cursor.execute("""
        SELECT t.transaction_id, s.name, i.item_name, t.amount, t.timestamp
        FROM transactions t
        JOIN students s ON t.student_id = s.student_id
        JOIN items i ON t.item_id = i.item_id
        WHERE DATE(t.timestamp) = %s
        ORDER BY t.timestamp DESC
    """, (today,))
    
    transactions = cursor.fetchall()
    cursor.close()
    return jsonify(transactions)


@app.route('/transactions', methods=['GET'])
def get_all_transactions():
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM transactions")
    transactions = cursor.fetchall()
    cursor.close()
    return jsonify(transactions)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)