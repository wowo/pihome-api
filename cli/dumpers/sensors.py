#!/usr/bin/python

from abstract_dumper import AbstractDumper
import sys

class TemperatureDumper(AbstractDumper):
    def dump_data(self, output_path):
        output_path = output_path.rstrip('/')
        logger = self.get_logger()
        file_handlers = {}

        criteria = {'user': {'$exists': True, '$ne': None}}
        iterator = self.get_db().switches.find(criteria).sort('date', -1)
        for document in iterator:
            print(document)
            path = '%s/switches.json' % output_path
            filename = '%s/data-%d-%02d.csv' % (
                path,
                document['date'].year,
                document['date'].month)
            self.ensure_dirs(path)
            logger.debug('Attempting to write data to file %s' % filename)
            file = open(filename, 'w+') # dict of files needed
            # todo proper file structure here
            file.write(str(document))

        file.close()

if len(sys.argv) == 1:
    raise Exception('Please specify output path as first argument')

dumper = TemperatureDumper()
dumper.dump_data(sys.argv[1].rstrip('/'))