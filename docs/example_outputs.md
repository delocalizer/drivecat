## Tree format

```bash
drivecat output store.db -format tree
```
output:
```
My Drive/ [owner:user:John Doe <jd@gmail.com>]
├── Documents/ [owner:user:John Doe <jd@gmail.com>|writer:user:Jane Doe <jd@myuni.edu.au>]
│   ├── CINECA_Use Cases_v1.0.pdf [owner:user:John Doe <jd@gmail.com>|writer:user:Jane Doe <jd@myuni.edu.au>]
⋮
```
## TSV format
```
drivecat output store.db -format tsv
```
output:
```
My Drive:/	[owner:user:John Doe <jd@gmail.com>]
My Drive:/Documents	[owner:user:John Doe <jd@gmail.com>|writer:user:Jane Doe <jd@myuni.edu.au>]
My Drive:/Documents/CINECA_Use Cases_v1.0.pdf	[owner:user:John Doe <jd@gmail.com>|writer:user:Jane Doe <jd@myuni.edu.au>]
…
```

## NDJSON format
```
drivecat output store.db -format ndjson | jq .
```
output:
```
{
  "depth": 0,
  "drive_id": null,
  "id": "vvvvvv",
  "mime_type": "application/vnd.google-apps.folder",
  "modified_time": "2010-05-31T23:16:58.145Z",
  "name": "My Drive",
  "owners": [
    "jd@gmail.com"
  ],
  "parent_ids": [],
  "path": "My Drive:/",
  "path_segments": [
    "My Drive"
  ],
  "permissions": [
    {
      "displayName": "John Doe",
      "domain": null,
      "emailAddress": "jd@gmail.com",
      "id": "123456789",
      "role": "owner",
      "type": "user"
    }
  ],
  "permissions_display": "[owner:user:John Doe <jd@gmail.com>]",
  "size": null,
  "web_view_link": "https://drive.google.com/drive/folders/vvvvvv"
}
{
  "depth": 1,
  "drive_id": null,
  "id": "wwwwww",
  "mime_type": "application/vnd.google-apps.folder",
  "modified_time": "2021-12-02T04:15:54.760Z",
  "name": "Documents",
  "owners": [
    "jd@gmail.com"
  ],
  "parent_ids": [
    "vvvvvv"
  ],
  "path": "My Drive:/Documents",
  "path_segments": [
    "My Drive",
    "Documents"
  ],
  "permissions": [
    {
      "displayName": "John Doe",
      "domain": null,
      "emailAddress": "jd@gmail.com",
      "id": "123456789",
      "role": "owner",
      "type": "user"
    },
    {
      "displayName": "Jane Doe",
      "domain": null,
      "emailAddress": "jd@myuni.edu.au",
      "id": "987654321",
      "role": "writer",
      "type": "user"
    }
  ],
  "permissions_display": "[owner:user:John Doe <jd@gmail.com>|writer:user:Jane Doe <jd@myuni.edu.au>]",
  "size": null,
  "web_view_link": "https://drive.google.com/drive/folders/wwwwww"
}
{
  "depth": 2,
  "drive_id": null,
  "id": "xxxxxx",
  "mime_type": "application/pdf",
  "modified_time": "2021-09-30T09:48:28.000Z",
  "name": "CINECA_Use Cases_v1.0.pdf",
  "owners": [
    "jd@gmail.com"
  ],
  "parent_ids": [
    "wwwwww"
  ],
  "path": "My Drive:/Documents/CINECA_Use Cases_v1.0.pdf",
  "path_segments": [
    "My Drive",
    "Documents",
    "CINECA_Use Cases_v1.0.pdf"
  ],
  "permissions": [
    {
      "displayName": "John Doe",
      "domain": null,
      "emailAddress": "jd@gmail.com",
      "id": "123456789",
      "role": "owner",
      "type": "user"
    },
    {
      "displayName": "Jane Doe",
      "domain": null,
      "emailAddress": "jd@myuni.edu.au",
      "id": "987654321",
      "role": "writer",
      "type": "user"
    }
  ],
  "permissions_display": "[owner:user:John Doe <jd@gmail.com>|writer:user:Jane Doe <jd@myuni.edu.au>]",
  "size": "659725",
  "web_view_link": "https://drive.google.com/file/d/xxxxxx/view?usp=drivesdk"
}
