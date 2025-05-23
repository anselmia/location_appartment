echo "⚙️  Step 1: Activate virtualenv"
source ./venv/Scripts/activate || source ./venv/bin/activate

echo "✅ Virtualenv activated"

echo "📦 Step 2: Install requirements"
pip install -r requirements.txt

echo "✅ Requirements installed"

echo "🛠 Step 3: Run makemigrations"
python manage.py makemigrations

echo "✅ Migrations generated"

echo "📂 Step 4: Apply all migrations"
python manage.py migrate

echo "✅ Database migrated"

echo "🏙 Step 5: Import major cities (Alpes-Maritimes)"
python manage.py import_major_cities

echo "✅ Cities imported"

echo "🎯 Step 6: Create discount types"
python manage.py create_discount_types

echo "✅ Discount types imported"

echo "🔌 Step 7: Import equipment"
python manage.py import_equipment

echo "✅ Equipment imported"

echo "👤 Step 8: Create superuser"
python manage.py createsuperuser

echo "✅ Superuser created"
