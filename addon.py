'''
    OneDrive for Kodi
    Copyright (C) 2015 - Carlos Guzman

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

    Created on Mar 1, 2015
    @author: Carlos Guzman (cguZZman) carlosguzmang@hotmail.com
'''
from clouddrive.common.messaging.listener import CloudDriveMessagingListerner
from clouddrive.common.ui.addon import CloudDriveAddon
from clouddrive.common.utils import Utils
from resources.lib.provider.onedrive import OneDrive
import datetime
from clouddrive.common.cache.simplecache import SimpleCache
import urllib


class OneDriveAddon(CloudDriveAddon, CloudDriveMessagingListerner):
    _provider = OneDrive()
    _extra_parameters = {'expand': 'thumbnails'}
    _cache = None
    
    def __init__(self):
        self._cache = SimpleCache()
        self._cache.enable_mem_cache = False
        super(OneDriveAddon, self).__init__()
        
    def get_provider(self):
        return self._provider
    
    def get_custom_drive_folders(self, driveid=None):
        drive_folders = [
            {'name' : self._common_addon.getLocalizedString(32058), 'folder' : 'sharedWithMe'},
            {'name' : self._common_addon.getLocalizedString(32053), 'folder' : 'recent'}
        ]
        if self._content_type == 'image':
            drive_folders.append({'name' : self._addon.getLocalizedString(32007), 'folder' : 'special/photos'})
            drive_folders.append({'name' : self._addon.getLocalizedString(32008), 'folder' : 'special/cameraroll'})
        elif self._content_type == 'audio':
            drive_folders.append({'name' : self._addon.getLocalizedString(32009), 'folder' : 'special/music'})
        return drive_folders

    def get_folder_items(self, driveid=None, item_driveid=None, item_id=None, folder=None, on_items_page_completed=None):
        self._provider.configure(self._account_manager, driveid)
        if item_id:
            files = self._provider.get('/drives/'+item_driveid+'/items/' + item_id + '/children', parameters = self._extra_parameters)
        elif folder == 'sharedWithMe' or folder == 'recent':
            files = self._provider.get('/drives/'+driveid+'/' + folder)
        else:
            files = self._provider.get('/drives/'+driveid+'/' + folder + '/children', parameters = self._extra_parameters)
        if self.cancel_operation():
            return
        return self.process_files(files, on_items_page_completed)
    
    def search(self, query, driveid=None, item_driveid=None, item_id=None, on_items_page_completed=None):
        self._provider.configure(self._account_manager, driveid)
        url = '/drives/'
        if item_id:
            url += item_driveid+'/items/' + item_id
        else:
            url += driveid
        url += '/search(q=\''+urllib.quote(query)+'\')'
        self._extra_parameters['filter'] = 'file ne null'
        files = self._provider.get(url, parameters = self._extra_parameters)
        if self.cancel_operation():
            return
        return self.process_files(files, on_items_page_completed)
    
    def process_files(self, files, on_items_page_completed=None):
        items = []
        for f in files['value']:
            f = Utils.get_safe_value(f, 'remoteItem', f)
            item = self._extract_item(f)
            cache_key = self._addon_id+'-'+'item-'+item['drive_id']+'-'+item['id']
            self._cache.set(cache_key, f, expiration=datetime.timedelta(minutes=1))
            items.append(item)
        if on_items_page_completed:
            on_items_page_completed(items)
        if '@odata.nextLink' in files:
            next_files = self._provider.get(files['@odata.nextLink'])
            if self.cancel_operation():
                return
            items.extend(self.process_files(next_files, on_items_page_completed))
        return items
    
    def _extract_item(self, f, include_download_info=False):
        item = {
            'id': f['id'],
            'name': f['name'],
            'name_extension' : Utils.get_extension(f['name']),
            'drive_id' : Utils.get_safe_value(Utils.get_safe_value(f, 'parentReference', {}), 'driveId'),
            'mimetype' : Utils.get_safe_value(Utils.get_safe_value(f, 'file', {}), 'mimeType')
        }
        if 'folder' in f:
            item['folder'] = {
                'child_count' : f['folder']['childCount']
            }
        if 'video' in f:
            video = f['video']
            item['video'] = {
                'width' : video['width'],
                'height' : video['height'],
                'duration' : video['duration']/1000
            }
        if 'audio' in f:
            audio = f['audio']
            item['audio'] = {
                'tracknumber' : Utils.get_safe_value(audio, 'track'),
                'discnumber' : Utils.get_safe_value(audio, 'disc'),
                'duration' : int(Utils.get_safe_value(audio, 'duration') or '0') / 1000,
                'year' : Utils.get_safe_value(audio, 'year'),
                'genre' : Utils.get_safe_value(audio, 'genre'),
                'album': Utils.get_safe_value(audio, 'album'),
                'artist': Utils.get_safe_value(audio, 'artist'),
                'title': Utils.get_safe_value(audio, 'title')
            }
        if 'image' in f or 'photo' in f:
            item['image'] = {
                'size' : f['size']
            }
        if 'thumbnails' in f and len(f['thumbnails']) > 0:
            thumbnails = f['thumbnails'][0]
            item['thumbnail'] = thumbnails['large']['url']
        if include_download_info:
            item['download_info'] =  {
                'url' : Utils.get_safe_value(f,'@microsoft.graph.downloadUrl'),
                'headers' : {
                    'authorization' : 'Bearer ' + self._provider.get_access_tokens()['access_token']
                }
            }
        return item
    
    def get_item(self, driveid=None, item_driveid=None, item_id=None, folder=None, find_subtitles=False, include_download_info=False):
        self._provider.configure(self._account_manager, driveid)
        cache_key = self._addon_id+'-'+'item-'+Utils.str(item_driveid)+'-'+Utils.str(item_id)+'-'+Utils.str(folder)
        f = self._cache.get(cache_key)
        if not f :
            if item_id:
                f = self._provider.get('/drives/'+item_driveid+'/items/' + item_id, parameters = self._extra_parameters)
            elif folder == 'sharedWithMe' or folder == 'recent':
                return
            else:
                f = self._provider.get('/drives/'+driveid+'/' + folder, parameters = self._extra_parameters)
            self._cache.set(cache_key, f, expiration=datetime.timedelta(seconds=59))
        item = self._extract_item(f, include_download_info)
        if find_subtitles:
            subtitles = []
            parent_id = Utils.get_safe_value(Utils.get_safe_value(f, 'parentReference', {}), 'id')
            search_url = '/drives/'+item_driveid+'/items/' + parent_id + '/search(q=\'{'+urllib.quote(Utils.remove_extension(item['name']))+'}\')'
            files = self._provider.get(search_url)
            for f in files['value']:
                subtitle = self._extract_item(f, include_download_info)
                if subtitle['name_extension'] == 'srt' or subtitle['name_extension'] == 'sub' or subtitle['name_extension'] == 'sbv':
                    subtitles.append(subtitle)
            if subtitles:
                item['subtitles'] = subtitles
        return item

if __name__ == '__main__':
    OneDriveAddon().route()

