"""
tests/conftest.py
Shared pytest fixtures. Uses an in-memory SQLite database for tests
(configured via TestingConfig in config.py) so tests never touch the
real Supabase database and run fast with no network dependency.

NOTE: pytest-flask is installed but disabled via pytest.ini's
'-p no:flask' addopts flag, since its own 'app'/'client' fixtures
conflict with the ones we define below (pytest-flask expects a
different app factory contract than our create_app() pattern).

Run all tests with:
    pytest

Run a specific file:
    pytest tests/test_inventory_service.py

Run with verbose output:
    pytest -v
"""

import pytest
from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models import User, Category, Product


@pytest.fixture
def app():
    """Fresh Flask app + in-memory DB for each test function."""
    app = create_app("testing")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def customer_user(app):
    user = User(
        first_name="Test", last_name="Customer", email="customer@test.com",
        role="customer", agreed_to_terms=True, agreed_to_terms_at=datetime.now(timezone.utc),
    )
    user.set_password("TestPass123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(app):
    user = User(
        first_name="Test", last_name="Admin", email="admin@test.com",
        role="admin", agreed_to_terms=True, agreed_to_terms_at=datetime.now(timezone.utc),
    )
    user.set_password("AdminPass123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def sample_category(app):
    category = Category(name="Test Category", slug="test-category", illustration="noto:box")
    db.session.add(category)
    db.session.commit()
    return category


@pytest.fixture
def sample_product(app, sample_category):
    product = Product(
        name="Test Product", brand="Test Brand", description="A product for testing",
        category_id=sample_category.id, subcategory_name="Test Subcategory",
        price=100.00, unit="per piece", sku="TEST-001", stock=20, low_stock_threshold=5,
    )
    db.session.add(product)
    db.session.commit()
    return product


def auth_headers(client, email: str, password: str) -> dict:
    """Helper to log in and return an Authorization header dict for use
    in subsequent test requests."""
    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    token = response.get_json()["accessToken"]
    return {"Authorization": f"Bearer {token}"}