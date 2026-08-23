# coding: utf-8

from django.utils import translation

try:
    from cms.plugins.text.models import Text
    from cms.plugins.text.utils import plugin_tags_to_id_list
except ImportError:
    from djangocms_text_ckeditor.models import Text
    from djangocms_text_ckeditor.utils import plugin_tags_to_id_list

from cms.models import CMSPlugin
from .models import Footnote
from .settings import CMSPLUGIN_FOOTNOTE_DEBUG


def _page_placeholders(page, language):
    """The page's placeholders, on both django CMS versions.

    django CMS 3.x: placeholders hang off the page and are language
    independent. django CMS 4.1: they belong to the language's PageContent,
    and ``Page.get_placeholders(language)`` sees published content only
    (under djangocms-versioning) -- which is what footnote rendering wants:
    a page with no published content in the language has no footnotes.

    # REMOVE AT: hop 4 (django CMS 4.1 only) -- inline the CMS 4 branch.
    """
    try:
        from cms.models import PageContent   # django CMS 4.1
    except ImportError:                      # django CMS 3.x
        return page.get_placeholders()
    from cms.models import Placeholder
    try:
        return page.get_placeholders(language)
    except PageContent.DoesNotExist:
        return Placeholder.objects.none()


def get_footnotes_for_page(request, page):
    """
    Gets the Footnote instances for `page`, with the correct order.
    """
    language = translation.get_language()
    # django CMS 3.11's cms.utils.moderator.get_cmsplugin_queryset was a
    # deprecated alias for exactly this queryset; the module is gone in 4.1.
    # Placeholder.page is a plain FK only on CMS 3, so the page filter goes
    # through the page's placeholders instead of placeholder__page.
    footnote_and_text_plugins = CMSPlugin.objects.filter(
        placeholder__in=_page_placeholders(page, language),
        plugin_type__in=('FootnotePlugin', 'TextPlugin'),
        language=language,
    ).order_by('position').values('parent', 'plugin_type', 'pk')

    pks = [p['pk'] for p in footnote_and_text_plugins]
    footnote_dict = Footnote.objects.in_bulk(pks)
    text_dict = Text.objects.in_bulk(pks)

    def get_footnote_or_text(plugin_pk, plugin_type):
        d = footnote_dict if plugin_type == 'FootnotePlugin' else text_dict
        try:
            return d[plugin_pk]
        except KeyError:
            if CMSPLUGIN_FOOTNOTE_DEBUG:
                raise

    root_footnote_and_text_plugins = [p for p in footnote_and_text_plugins
                                      if p['parent'] is None]

    footnotes = []
    for plugin in root_footnote_and_text_plugins:
        footnote_or_text = get_footnote_or_text(plugin['pk'],
                                                plugin['plugin_type'])
        if footnote_or_text is None:
            continue
        if plugin['plugin_type'] == 'FootnotePlugin':
            footnotes.append(footnote_or_text)
        else:
            for pk in plugin_tags_to_id_list(footnote_or_text.body):
                footnote = get_footnote_or_text(pk, 'FootnotePlugin')
                if footnote is not None:
                    footnotes.append(footnote)
    return footnotes
