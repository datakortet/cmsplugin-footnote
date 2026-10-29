# -*- coding: utf-8 -*-
"""Test settings: django CMS 4.1 and 5.0 with djangocms-versioning.

Modeled on cmspagetools/dkstructdoc's conftests (hop 3).
"""
import os

import django
import pytest

DIRNAME = os.path.dirname(__file__)


def _installed_apps():
    """The app list. django CMS 4.1+ needs djangocms-versioning."""
    import importlib.util

    import cms

    apps = [
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.admin',
        'django.contrib.sites',
        'django.contrib.staticfiles',
        'treebeard',
        'menus',
        'sekizai',
        'cms',
        'djangocms_text_ckeditor',
        'cmsplugin_footnote',
    ]
    if importlib.util.find_spec('djangocms_versioning') is None:
        raise RuntimeError(
            f'django CMS {cms.__version__} requires djangocms-versioning,'
            ' which is not installed.')
    apps.append('djangocms_versioning')
    return apps


def pytest_configure():
    from django.conf import settings
    settings.configure(
        DEBUG=True,
        SECRET_KEY='cmsplugin-footnote-tests',
        SITE_ID=1,
        ROOT_URLCONF='tests.urls',
        USE_TZ=True,
        LANGUAGE_CODE='nb',
        LANGUAGES=(('nb', 'Norsk'),),
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
        ],
        TEMPLATES=[{
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [os.path.join(DIRNAME, 'templates')],
            'APP_DIRS': True,
            'OPTIONS': {
                'context_processors': [
                    'django.contrib.auth.context_processors.auth',
                    'django.contrib.messages.context_processors.messages',
                    'django.template.context_processors.request',
                    'sekizai.context_processors.sekizai',
                ],
            },
        }],
        CMS_TEMPLATES=[('footnote-test.html', 'Test template')],
        # required by the django CMS 4.1+ pre_migrate guard
        CMS_CONFIRM_VERSION4=True,
        STATIC_URL='/static/',
        INSTALLED_APPS=tuple(_installed_apps()),
    )
    django.setup()


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_superuser(
        'admin', 'admin@example.invalid', 'secret')


@pytest.fixture
def page(user):
    """A page with 'nb' content, published."""
    from cms.api import create_page
    page = create_page('Fotnoter', 'footnote-test.html', 'nb',
                       created_by=user)
    publish(page, 'nb', user)
    return page


def publish(page, language, user):
    """Publish through djangocms-versioning. Test support only."""
    from cms.models import PageContent
    content = PageContent.admin_manager.filter(
        page=page, language=language).first()
    return content.versions.first().publish(user)


def content_placeholder(page, language='nb', slot='content'):
    """The page's ``slot`` placeholder. Test support only."""
    placeholders = page.get_placeholders(language, admin_manager=True)
    return placeholders.get(slot=slot)
