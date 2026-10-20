"""GUI resume policy: reuse verified files without renaming existing originals."""
from gdt_tax.storage import ZipStore

from .documents import KINDS, document_id, verify_rows


class DesktopZipStore(ZipStore):
    def __init__(self, directory, logger=None, known_rows=()):
        super().__init__(directory, logger)
        self.known = {document_id('tax', row): row for row in known_rows}

    def find_existing(self, record):
        row = record.to_dict()
        prior = self.known.get(record.record_key, {})
        field = KINDS['tax'][2]
        if prior.get(field):
            row[field] = prior[field]
        verified = verify_rows('tax', [row], self.directory)[0]
        if verified['_file_status'] != 'downloaded':
            return None
        record.tep_zip = verified[field]
        self.logger.info('Bỏ qua ZIP đã có hợp lệ: %s', record.tep_zip)
        from pathlib import Path
        return Path(verified['_file_path'])
