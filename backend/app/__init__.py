# from flask import Flask
# from flask_sqlalchemy import SQLAlchemy
# from flask_cors import CORS
# import os

# db = SQLAlchemy()

# def create_app():
#     app = Flask(__name__)

#     app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
#         'DATABASE_URL',
#         'postgresql://taskuser:taskpassword@localhost:5432/taskmanager'
#     )
#     app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
#     app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

#     db.init_app(app)
#     CORS(app)

#     from app.routes import api_bp
#     app.register_blueprint(api_bp, url_prefix='/api')

#     with app.app_context():
#         db.create_all()
#         seed_users()

#     return app

# def seed_users():
#     from app.models import User
#     from werkzeug.security import generate_password_hash

#     if User.query.first() is None:
#         users = [
#             User(username='admin', password_hash=generate_password_hash('admin123')),
#             User(username='user', password_hash=generate_password_hash('user123')),
#         ]
#         for user in users:
#             db.session.add(user)
#         db.session.commit()













from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
import os

load_dotenv()

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
        'postgresql://taskuser:taskpassword@localhost:5432/taskmanager'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    db.init_app(app)
    CORS(app)

    from app.routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    with app.app_context(): 
        db.create_all()
        # Only seed users if the users table is empty
        from app.models import User
        from werkzeug.security import generate_password_hash
        
        if User.query.count() == 0:
            users = [
                User(username='admin', password_hash=generate_password_hash('admin123')),
                User(username='user', password_hash=generate_password_hash('user123')),
            ]
            for user in users:
                db.session.add(user)
            db.session.commit()
            print("Seeded default users")

    return app
