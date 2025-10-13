
import sys
import csv
import base64

# use me
# python3 decode_trap_images.py "./data.csv" 


def decode_images():

    if len(sys.argv) < 2:
        print('need to provide an absolute path to a stat browser csv export of camera stats')
        return

    # absolute path to stat browser export of camera stats
    absolute_path_to_export = sys.argv[1]

    with open(absolute_path_to_export, newline='') as stat_browser_export:
        spamreader = csv.DictReader(stat_browser_export, delimiter=',')
        try:
            for row in spamreader:

                image_data = row['image']

                # filter out the broken stuff
                #if not image_data or image_data.startswith('/lfs'):
                #    continue

                with open('{0}_{1}_{2}_{3}.png'.format(row['id'], row['ip_device_id'], row['auto_classification'], row['manual_classification']), 'wb') as fh:
                    # print(image_data)
                    fh.write(base64.b64decode(image_data))
        except Exception:
            pass


if __name__ == "__main__":
    decode_images()