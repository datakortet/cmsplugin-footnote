#!/usr/bin/env python
# coding: utf-8

from setuptools import setup, find_packages
from cmsplugin_footnote import version_string


setup(
    name='cmsplugin-footnote',
    version=version_string,
    author='Bertrand Bordage',
    author_email='bordage.bertrand@gmail.com',
    url='https://github.com/BertrandBordage/cmsplugin-footnote',
    description='A simple plugin allowing to add footnotes in django CMS.',
    long_description=open('README.rst').read(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP',
    ],
    license='BSD',
    packages=find_packages(),
    install_requires=[
        'Django >= 3.2',
        # tested on django CMS 4.1 and 5.0 (hop 5); 3.11 is no longer tested
        'django-cms >= 4.1, < 5.1',
        # hop 6: djangocms-text replaces it on Python 3.13 / Django 5.2
        "djangocms-text-ckeditor >= 5 ; python_version < '3.13'",
        "djangocms-text >= 1.0 ; python_version >= '3.13'",
    ],
    include_package_data=True,
    zip_safe=False,
)
