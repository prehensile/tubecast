import subprocess
from bs4 import BeautifulSoup as bs
from flask import Flask, Response, url_for, render_template, abort, request
import requests
import urlparse 
import sys, os, signal
import re
import datetime, time
from email import utils
from werkzeug.wrappers import Response as ResponseBase
from itunes_categories import valid_categories


MP3_BITRATE_K = 128
# AUDIO_FORMAT = "mp3"
# MIME_TYPE = "audio/mpeg"
AUDIO_FORMAT_MP3 = "mp3"
AUDIO_FORMAT_ADTS = "adts"

AUDIO_FORMAT = AUDIO_FORMAT_MP3
MIME_TYPE = "audio/mp3"

class StreamingResponse( ResponseBase ):
    
    def __init__( self, youtube_id=None, audio_format=None, headers=None ):
        
        # construct path to heroku vended ffmpeg first...
        ff_path = os.path.dirname(os.path.realpath(__file__))
        ff_path = os.path.join( ff_path, ".heroku/vendor/ffmpeg/bin/ffmpeg")
        is_heroku = True
        ## ...fall back to assuming it's in the system path
        if not os.path.exists( ff_path ):
            ff_path = "ffmpeg"
            is_heroku = False

        yt_args = [ "youtube-dl", "-f", "140", "-q", "--output", "-", youtube_id ]
        if audio_format == AUDIO_FORMAT_MP3:
            br = "%sk" % MP3_BITRATE_K
            acodec = "libmp3lame"
            ff_args = [ ff_path, "-loglevel", "quiet", "-i", "-", "-acodec", acodec, "-ab", br, "-ac", "2", "-ar", "44100", "-f", audio_format, "-" ]
        else:
            acodec = "libvo_aacenc"
            if is_heroku:
                # version of ffmpeg in heroku buildpack doesn't contain libvo_aacenc codec
                acodec = "libfaac"
            ff_args = [ ff_path, "-loglevel", "quiet", "-i", "-", "-vn", "-acodec", acodec, "-f", "adts", "-" ]

        #ff_args = [ ff_path, "-i", "-", "-acodec", "copy", "-vn", "-f", "adts", "-" ]
        #ff_args = [ ff_path, "-i", "-", "-acodec", "copy", "-vn", "-f", "mp4", "-movflags", "frag_keyframe", "-frag_size", "1024", "-" ]

        print " ".join(yt_args)
        print " ".join(ff_args)

        self._ff_proc = None
        self._yt_proc = None
        try:
            self._yt_proc = subprocess.Popen( yt_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid )
        except:
            pass
        try:
            self._ff_proc = subprocess.Popen( ff_args, stdin=self._yt_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid )    
        except:
            pass

        def stream():
            buf_size = 1024
            finished = False
            streamed = 0
            print "-> begin streaming..."
            while not finished:
                d = self._ff_proc.stdout.read( buf_size )
                yield d
                streamed += len(d)
                if len(d) < buf_size:
                    finished = True
            print "-> stream ended. Streamed %d bytes." % streamed

        response = None
        status = 500
        mimetype = None
        response = "Error"

        if (self._yt_proc is not None) and (self._ff_proc is not None):
            response = stream()
            status = 200
            mimetype = MIME_TYPE

        super( StreamingResponse, self ).__init__( response=response,
                                                    status=status,
                                                    headers=headers,
                                                    mimetype=mimetype,
                                                    content_type=None,
                                                    direct_passthrough=False ) 

        self.call_on_close( self.kill_threads )

    def kill_threads( self ):
        print "kill_threads, _ff_proc=%s, _yt_proc=%s" % ( self._ff_proc, self._yt_proc ) 
        if self._ff_proc is not None:
            print "--> kill ffmpeg"
            #self._ff_proc.wait()
            #self._ff_proc.terminate()
            try:
                os.killpg( self._ff_proc.pid, signal.SIGKILL )
            except Exception, e:
                self._ff_proc.kill()
                pass
            del self._ff_proc
            self._ff_proc = None
        if self._yt_proc is not None:
            print "--> kill youtube-dl"
            #self._yt_proc.wait()
            #self._yt_proc.terminate()
            try:
                os.killpg( self._yt_proc.pid, signal.SIGKILL )
            except Exception, e:
                self._yt_proc.kill()
            del self._yt_proc
            self._yt_proc = None
        print "kill_threads FINISHED"

app = Flask(__name__)
app.debug = True

@app.route('/')
def index():
    return render_template( "index.html" )

@app.route('/stream/<path:path>')
def stream( path ):
    
    # check we've got the path format we're expecting    
    path_components = path.split("/")
    if len(path_components) < 1:
        #TODO: more detailed error throwing
        abort(400)

    # separate the 'filename' into root & ext
    filename = path_components[0]
    root, ext = os.path.splitext( filename )
    youtube_id = root
    if not re.match( r'[a-zA-Z0-9_-]{11}', youtube_id ):
        #TODO: more detailed error throwing
        abort(400)


    mimetype = MIME_TYPE
    audio_format = ext[1:]
    headers = {
        # 'Content-Disposition' : 'attachment; filename=%s' % filename,
    }

    fs = 0
    if audio_format == AUDIO_FORMAT_MP3:
        d = request.args.get("d")
        if d:
            fs = get_filesize( d ) 
        headers['Content-length'] = fs

    # don't start streaming until we've been asked properly for audio data
    if request.accept_mimetypes[ mimetype ] < 1:
        print "-> return dummy stream"
        def stream():
            yield '0'
        return Response( stream(), mimetype=mimetype, headers=headers )

    print "content accepted"
    r = StreamingResponse( youtube_id=youtube_id, audio_format=audio_format, headers=headers )
    return r

def format_duration( seconds ):
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%d:%02d:%02d" % (h, m, s)    

def format_date( datestring ):
    # 2008-12-24T00:46:17.000Z
    dt = datetime.datetime.strptime( datestring, "%Y-%m-%dT%H:%M:%S.%fZ" )
    return utils.formatdate( time.mktime(dt.timetuple()) )

def parse_categories( tag ):
    tags = tag.find_all( "category",
        scheme="http://gdata.youtube.com/schemas/2007/categories.cat",
        recursive=False )
    categories = [ ctag.attrs["term"] for ctag in tags ]
    categories = [ category for category in categories if category in valid_categories ]
    return categories

def get_subtitle( text ):
    subtitle = ""
    if (text is not None) and (len(text) > 255):
        subtitle = text[:255]
    return subtitle

def get_comments( entry_tag ):
    comments = ""
    try:
        comments_tag = entry_tag.find("gd:comments")
        comments_link = comments_tag.find("gd:feedLink")
        comments = comments_link.attrs["href"]
    except Exception, e:
        pass
    return comments

def get_filesize( duration ):
    if AUDIO_FORMAT == AUDIO_FORMAT_MP3:
        duration = int(duration)
        return (duration * (MP3_BITRATE_K*1000)) / 8
    return 0

def get_media_url( yt_id, duration=0 ):
    media_url = None
    fn_media = "%s.%s" % ( yt_id, AUDIO_FORMAT )
    try:
        media_url = url_for( "stream", path=fn_media, _external=True, d=duration )
    except Exception, e:
        pass
    return media_url 

def get_feed_url( playlist_id ):
    feed_url = None
    try:
        feed_url = url_for( "feed", path=playlist_id, _external=True )
    except Exception, e:
        pass
    return( feed_url )

def parse_playlist( playlist_id ):

    feed_url = "http://gdata.youtube.com/feeds/api/playlists/" + playlist_id
    r = requests.get( feed_url )
    soup = bs( r.text )

    channel_out = {}
    items_out = []

    feed = soup.find("feed")
    
    channel_author = feed.find("author")
    channel_title = "tubecast: %s" % feed.find("title").string
    channel_subtitle = feed.find("subtitle").string
    if channel_subtitle is None:
        channel_subtitle = ""
    channel_description = channel_subtitle

    self_url = None
    try:
        self_url = url_for( "feed", path=playlist_id, _external=True )
    except Exception, e:
        pass
    channel_out["self_url"] = self_url
    channel_out["title"] = channel_title
    channel_out["subtitle"] = channel_subtitle
    channel_out["link"] = feed.find( "link", rel="alternate" ).attrs["href"]
    channel_out["description"] = channel_description
    channel_out["last_updated"] = format_date( feed.find("updated").string )
    channel_out["author"] = channel_author
    channel_out["author_name"] = channel_author.find("name").text
    channel_out["admin_email"] = "tubecast@prehensile.net"

    thumbnail = feed.find("media:group").find( "media:thumbnail", attrs={ "yt:name" : "default" } )
    channel_out["image_url"] = thumbnail["url"]
    channel_out["image_width"] = thumbnail["width"]
    channel_out["image_height"] = thumbnail["height"]

    it_image = feed.find("media:group").find( "media:thumbnail", attrs={ "yt:name" : "hqdefault" } )
    channel_out["it_image_url"] = it_image["url"]

    channel_out["keywords"] = ",".join([ "tubecast" ])
    channel_out["categories"] = parse_categories( feed )

    for entry_tag in soup.find_all( "entry" ):

        this_item = {}

        # extract a few things from the item xml
        media_group = entry_tag.find( "media:group" )
        media_player = media_group.find( "media:player" )
        player_url = media_player.attrs[ "url" ]
        item_author = entry_tag.find("author")
        item_duration = media_group.find( "media:content" ).attrs["duration"]
        item_description = entry_tag.find( "yt:description" ).text
        item_subtitle = get_subtitle( item_description )

        # get youtube item id from player url
        parsed = urlparse.urlparse( player_url )
        qd = urlparse.parse_qs( parsed.query )
        yt_id = "%s" % qd["v"][0]
        
        # construct item dict
        this_item["title"] = entry_tag.find("title").string
        this_item["subtitle"] = item_subtitle
        this_item["pub_date"] = format_date( entry_tag.find("published").string )
        this_item["guid"] = entry_tag.find("id").string
        this_item["content"] = item_description
        this_item["comments"] = get_comments( entry_tag )
        
        this_item["link"] = entry_tag.find( "link", rel="alternate" ).attrs["href"]
        this_item["media_url"] = get_media_url( yt_id, item_duration )
        this_item["length"] = 0

        this_item["author"] = item_author
        this_item["author_name"] = item_author.find("name").text
        
        keywords = ""
        try:
            keywords = media_group.find("keywords").text
        except Exception, e:
            pass
        this_item["keywords"] = keywords
        this_item["categories"] = parse_categories( entry_tag )

        this_item["duration"] = item_duration
        this_item["description"] = item_description

        this_item["mime_type"] = app.config["MIME_TYPE"]
        this_item["it_duration"] = format_duration( item_duration )
        this_item["filesize"] = get_filesize( item_duration )
        
        items_out.append( this_item )

    return channel_out, items_out


@app.route('/feed/<path:path>')
def feed( path ):
    path_components = path.split("/")
    if len(path_components) < 1:
        abort(400)

    playlist_id = path_components[0]
    if not re.match( r'[a-zA-Z0-9_-]+', playlist_id ):
        #TODO: better validation
        abort(400)

    #rendered = generate_feed( playlist_id )

    try:
        channel, items = parse_playlist( playlist_id )
    except Exception:
        #TODO: better error handling
        abort(500)
    
    rendered = render_template( "feed.xml",
                            channel=channel,
                            items=items )
    
    return Response( response=rendered,
                    status=200,
                    mimetype="application/xml")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        playlist_id = sys.argv[1]
        channel, items = parse_playlist( playlist_id )
        print channel
        print items
    else:
        app.run()
