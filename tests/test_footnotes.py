# -*- coding: utf-8 -*-
"""DB-backed behaviour of the footnote collector on both CMS tiers."""
import cms
import pytest
from cms.api import add_plugin
from cms.plugin_pool import plugin_pool
from django.core.management import call_command
from django.template import Template
from sekizai.context import SekizaiContext
from django.test import RequestFactory

from cmsplugin_footnote.models import Footnote
from cmsplugin_footnote.utils import get_footnotes_for_page

from .conftest import content_placeholder, publish

CMS4 = int(cms.__version__.split('.')[0]) >= 4


def make_request():
    request = RequestFactory().get('/')
    request.session = {}
    request.current_page = None
    return request


def test_plugin_is_registered():
    assert 'FootnotePlugin' in plugin_pool.plugins


def test_model_state_matches_migrations(db):
    call_command(
        'makemigrations', 'cmsplugin_footnote', '--check', '--dry-run',
        verbosity=0,
    )


def test_root_footnotes_in_position_order(page):
    ph = content_placeholder(page)
    first = add_plugin(ph, 'FootnotePlugin', 'nb', body='first', symbol='a')
    second = add_plugin(ph, 'FootnotePlugin', 'nb', body='second',
                        symbol='b')

    footnotes = get_footnotes_for_page(make_request(), page)

    # add_plugin assigns increasing positions on both tiers
    assert [f.pk for f in footnotes] == [first.pk, second.pk]
    assert all(isinstance(f, Footnote) for f in footnotes)


def test_footnote_inside_text_plugin(page):
    from djangocms_text_ckeditor.utils import plugin_to_tag

    ph = content_placeholder(page)
    text = add_plugin(ph, 'TextPlugin', 'nb', body='')
    note = add_plugin(ph, 'FootnotePlugin', 'nb', body='inline note',
                      target=text)
    text.body = plugin_to_tag(note)
    text.save()

    footnotes = get_footnotes_for_page(make_request(), page)

    assert [f.pk for f in footnotes] == [note.pk]


def test_other_pages_footnotes_are_not_included(page, user):
    from cms.api import create_page
    other = create_page('Andre', 'footnote-test.html', 'nb', created_by=user)
    publish(other, 'nb', user)
    add_plugin(content_placeholder(other), 'FootnotePlugin', 'nb',
               body='other page')

    assert get_footnotes_for_page(make_request(), page) == []


@pytest.mark.skipif(not CMS4, reason='published-only lookup is CMS 4 only')
def test_unpublished_page_has_no_footnotes_on_cms4(user):
    from cms.api import create_page
    draft = create_page('Utkast', 'footnote-test.html', 'nb',
                        created_by=user)
    add_plugin(content_placeholder(draft), 'FootnotePlugin', 'nb',
               body='draft note')

    assert get_footnotes_for_page(make_request(), draft) == []


def test_footnote_list_template_tag(page):
    add_plugin(content_placeholder(page), 'FootnotePlugin', 'nb',
               body='note body', symbol='*')
    request = make_request()
    # SekizaiContext: footnote_list.html addtoblock's its stylesheet
    out = Template(
        '{% load footnote %}{% footnote_list page %}'
    ).render(SekizaiContext({'request': request, 'page': page}))

    assert 'note body' in out
