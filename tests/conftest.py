# -*- coding: utf-8 -*-
"""Two-tier test settings: django CMS 3.x and 4.1 with djangocms-versioning.

Modeled on cmspagetools/dkstructdoc's conftests (hop 3).
"""
import os

import django
import pytest

DIRNAME = os.path.dirname(__file__)


def _installed_apps():
    """The app list, plus djangocms-versioning on django CMS 4.

       # REMOVE AT: hop 4 (django CMS 4.1 only) -- always install versioning.
    """
    import importlib.util

    import cms
    cms4 = int(cms.__version__.split('.')[0]) >= 4

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
    if cms4:
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
        # no-op on django CMS 3.x; required by the CMS 4.1 pre_migrate guard
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
    """A page with 'nb' content, published on both tiers."""
    from cms.api import create_page
    page = create_page('Fotnoter', 'footnote-test.html', 'nb',
                       created_by=user)
    publish(page, 'nb', user)
    return page


def publish(page, language, user):
    """Publish on either tier. Test support only.

       # REMOVE AT: hop 4 (django CMS 4.1 only) -- keep the versioning arm.
    """
    try:
        from cms.models import PageContent   # django CMS 4.1
    except ImportError:                      # django CMS 3.x
        return page.publish(language)
    content = PageContent.admin_manager.filter(
        page=page, language=language).first()
    return content.versions.first().publish(user)


def content_placeholder(page, language='nb', slot='content'):
    """The page's ``slot`` placeholder on either tier. Test support only."""
    try:
        placeholders = page.get_placeholders(language, admin_manager=True)
    except TypeError:                        # django CMS 3.x: no arguments
        placeholders = page.get_placeholders()
    return placeholders.get(slot=slot)
