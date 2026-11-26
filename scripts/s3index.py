"""Copy s3pypi's index.html to its package directory object and verify it.

   ``s3pypi upload --index.html`` writes ``<package>/index.html``, which the
   S3 website endpoint (``http://<bucket>/<package>/``) serves for the
   directory. The HTTPS REST endpoint
   (``https://s3.<region>.amazonaws.com/<bucket>/<package>/``) serves the
   literal ``<package>/`` object instead. s3pypi never writes that object,
   so pip installing over HTTPS read stale hashes after a publish
   (dktools#4).

   Run it after ``s3pypi upload``, with the same distribution files::

       python s3index.py --bucket BUCKET --url URL [--acl ACL] dist/*

   For each package it checks that ``index.html`` lists the files' sha256
   hashes, copies exactly that ``index.html`` to ``<package>/``, and reads
   the directory, ``index.html`` and the files back anonymously from
   ``URL``. Any mismatch exits non-zero, which fails the publish.

   The script needs only the standard library and boto3, which s3pypi
   installs. ``ci-templates/wheel.yml`` embeds a verbatim copy of this file,
   and ``tests/test_s3index.py`` fails when the two differ.
"""
import argparse
import glob
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# the file types s3pypi.core.parse_distribution_id accepts
DISTRIBUTIONS = ('.whl', '.tar.gz', '.tar.bz2', '.tar.xz', '.zip')
# s3pypi.index.Index.to_html: <a href="{quote(filename)}#sha256={digest}">
LINK = re.compile(r'<a href="([^"#]+)#sha256=([0-9a-f]{64})">')
# s3pypi.storage.S3Storage.put_index serves index pages with this
CACHE_CONTROL = 'public, must-revalidate, proxy-revalidate, max-age=0'


class IndexSyncError(Exception):
    """The directory object does not serve what was published."""


class IndexChanged(IndexSyncError):
    """index.html was replaced during the sync, by a concurrent publish."""


def package_directory(filename):
    """Return the S3 directory s3pypi uploads ``filename`` to.

       Mirrors ``parse_distribution_id`` and ``normalize_package_name`` in
       ``s3pypi.core``.
    """
    ext = next((e for e in DISTRIBUTIONS if filename.endswith(e)), None)
    if ext is None:
        raise IndexSyncError(f'not a distribution file: {filename}')
    stem = filename[:-len(ext)]
    if ext == '.whl':
        name = stem.split('-', 1)[0]
    else:
        name = stem.rsplit('-', 1)[0]
    return re.sub(r'[-_.]+', '-', name.lower())


def find_distributions(patterns):
    """Return the files s3pypi uploads for ``patterns``, e.g. ``dist/*``.

       As in s3pypi, a pattern the shell did not expand (cmd.exe) is globbed
       here, skipping the non-distribution files it matches.
    """
    paths = []
    for pattern in patterns:
        if os.path.isfile(pattern):
            paths.append(pattern)
            continue
        matches = sorted(path for path in glob.glob(pattern)
                         if os.path.isfile(path)
                         and path.endswith(DISTRIBUTIONS))
        if not matches:
            raise IndexSyncError(f'no distribution files match {pattern}')
        paths.extend(matches)
    return paths


def sha256(data):
    """Return the hex sha256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def parse_index(html):
    """Return ``{filename: sha256}`` for the links in an s3pypi index page."""
    return {urllib.parse.unquote(href): digest
            for href, digest in LINK.findall(html.decode('utf-8'))}


def fetch(url):
    """Return the body of an anonymous GET of ``url``, as pip sees it."""
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read()
    except urllib.error.URLError as e:
        raise IndexSyncError(f'GET {url} failed: {e}') from e


class Bucket:
    """An s3pypi bucket: written through the boto3 client ``s3``, verified
       anonymously through its public HTTPS base ``url``.
    """

    def __init__(self, s3, name, url, acl=None):
        self.s3 = s3
        self.name = name
        self.url = url.rstrip('/')
        self.acl = acl

    def read_index(self, directory, files):
        """Return the body and ETag of ``<directory>/index.html``.

           ``files`` maps each uploaded filename to its sha256, and the
           index must list every one of them with that hash.
        """
        key = f'{directory}/index.html'
        response = self.s3.get_object(Bucket=self.name, Key=key)
        html = response['Body'].read()
        listed = parse_index(html)
        for filename, digest in sorted(files.items()):
            if listed.get(filename) != digest:
                raise IndexSyncError(
                    f'{key} lists {filename} with sha256 '
                    f'{listed.get(filename)}, the uploaded file has {digest}')
        return html, response['ETag']

    def copy_index(self, directory, etag):
        """Copy ``<directory>/index.html`` to ``<directory>/``, provided the
           index still has ``etag``.
        """
        key = f'{directory}/index.html'
        extra = {'ACL': self.acl} if self.acl else {}
        try:
            self.s3.copy_object(
                Bucket=self.name, Key=f'{directory}/',
                CopySource={'Bucket': self.name, 'Key': key},
                CopySourceIfMatch=etag, MetadataDirective='REPLACE',
                ContentType='text/html', CacheControl=CACHE_CONTROL, **extra)
        except Exception as e:  # botocore.exceptions.ClientError
            error = getattr(e, 'response', {}).get('Error', {})
            if error.get('Code') != 'PreconditionFailed':
                raise
            raise IndexChanged(f'{key} changed before the copy') from e

    def verify(self, directory, html, files):
        """Check what pip sees: both index URLs serve ``html``, and every
           uploaded file matches its sha256.
        """
        base = f'{self.url}/{urllib.parse.quote(directory)}/'
        if fetch(base + 'index.html') != html:
            raise IndexChanged(f'{base}index.html changed after the copy')
        if fetch(base) != html:
            raise IndexSyncError(
                f'{base} does not serve {directory}/index.html')
        for filename, digest in sorted(files.items()):
            if sha256(fetch(base + urllib.parse.quote(filename))) != digest:
                raise IndexSyncError(
                    f'{base}{filename} does not match the uploaded file')

    def sync_package(self, directory, files):
        """Make ``<directory>/`` serve the index of the uploaded ``files``."""
        html, etag = self.read_index(directory, files)
        self.copy_index(directory, etag)
        self.verify(directory, html, files)

    def sync(self, patterns, attempts=3, delay=10):
        """Sync the directory object of every package in ``patterns``.

           Retries when a concurrent publish replaces index.html mid-sync;
           any other mismatch fails immediately.
        """
        packages = {}
        for path in find_distributions(patterns):
            with open(path, 'rb') as fp:
                digest = sha256(fp.read())
            filename = os.path.basename(path)
            packages.setdefault(package_directory(filename), {})[filename] = (
                digest)

        for directory, files in sorted(packages.items()):
            for attempt in range(1, attempts + 1):
                try:
                    self.sync_package(directory, files)
                    break
                except IndexChanged as e:
                    if attempt == attempts:
                        raise
                    print(f'{e}; retrying in {delay}s')
                    time.sleep(delay)
            print(f'{directory}/ serves {directory}/index.html, verified for '
                  f'{", ".join(sorted(files))}')


def main(argv=None):
    """Command line entry point, see the module docstring."""
    parser = argparse.ArgumentParser(
        description='Copy s3pypi index.html objects to their package '
                    'directory objects and verify them over HTTPS.')
    parser.add_argument('--bucket', required=True, help='the S3 bucket')
    parser.add_argument('--url', required=True,
                        help='public HTTPS base URL of the bucket, e.g. '
                             'https://s3.eu-west-1.amazonaws.com/BUCKET')
    parser.add_argument('--acl', help='canned ACL for the directory object')
    parser.add_argument('dist', nargs='+',
                        help='the files s3pypi uploaded, e.g. dist/*')
    args = parser.parse_args(argv)

    # installed with s3pypi, which is not a dktools requirement
    import boto3  # pylint: disable=import-outside-toplevel,import-error

    bucket = Bucket(boto3.client('s3'), args.bucket, args.url, acl=args.acl)
    try:
        bucket.sync(args.dist)
    except IndexSyncError as e:
        sys.exit(f'ERROR: {e}')


if __name__ == '__main__':
    main()
