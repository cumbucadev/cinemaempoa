#!/bin/bash

# Creates a backup of the database and sends to google drive
# this script needs sqlite3 and rclone installed

# apt-get install sqlite3 -y
# curl -O https://downloads.rclone.org/rclone-current-linux-amd64.zip
# unzip rclone-current-linux-amd64.zip
# cd rclone-*-linux-amd64
# cp rclone /usr/bin/
# chown root:root /usr/bin/rclone
# chmod 755 /usr/bin/rclone

# Follow https://rclone.org/drive/#making-your-own-client-id to set up a google drive client
# and then run `rclone config` to set the client id and secret locally
# use `google-drive` as the remote name

sqlite3 --version > /dev/null 2>&1
if [ $? != "0" ]; then
	echo "sqlite3 not found";
	exit 1;
fi

rclone --version > /dev/null 2>&1
if [ $? != "0" ]; then
	echo "rclone not found";
	exit 1;
fi

current_ymd=$(date -I)
SOURCE_DB="flask_backend.sqlite"
TARGET_DB="$current_ymd.sqlite"

WITH_DATA=(cinemas movies screenings screening_dates)
SCHEMA_ONLY=(users)

DRIVE_URL="https://drive.google.com/drive/u/0/folders/1f9qFHb2Fxdg_EGg3Vq4W-leDaGed9kXk"
BACKUPS_DIR="/home/ubuntu/cinemaempoa_db_backups/"

echo "Creating $TARGET_DB from $SOURCE_DB";

sqlite3 "$TARGET_DB" <<EOF
ATTACH '$SOURCE_DB' AS old;
$(for tbl in "${WITH_DATA[@]}"; do
  echo "CREATE TABLE $tbl AS SELECT * FROM old.$tbl;"
done)
DETACH old;
EOF

for tbl in "${SCHEMA_ONLY[@]}"; do
  echo "Copying schema for $tbl"
  sqlite3 "$SOURCE_DB" ".schema $tbl" | sqlite3 "$TARGET_DB"
done

echo 'INSERT INTO users (username, password) VALUES ("cinemaempoa", "scrypt:32768:8:1$6wcWOINh4waN54s2$919c10c0b4753255a8866b9b048c14d0e9083743e6435ebf75eb9cd30410594fef4455f418e02c783308bf27abed9a8802d6680ca71a98b7248caf30c74bb12a")' | sqlite3 "$TARGET_DB";

echo "Done. Created $TARGET_DB";

rclone sync "$TARGET_DB" google-drive:/cinemaempoa_backups

if [ $? != "0" ]; then
	echo "Error syncing file with rclone. Exiting";
	rm "$TARGET_DB";
	exit 1;
fi

echo "Backed up $TARGET_DB over to $DRIVE_URL";

mv "$TARGET_DB" "$BACKUPS_DIR$TARGET_DB" > /dev/null 2>&1

if [ $? != "0" ]; then
	echo "Couldn't move $TARGET_DB over to $BACKUPS_DIR. Removing file"
	rm "$TARGET_DB"
fi
