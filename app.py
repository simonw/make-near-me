from sanic import Sanic
from sanic import response
from sanic.views import HTTPMethodView
from jinja2 import Environment, FileSystemLoader
import os
import json
import re
import requests
import hashlib
import keen
from functools import wraps
from pathlib import Path
from itsdangerous import BadSignature, Signer

TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1,shrink-to-fit=no">
    <meta name="theme-color" content="#000000">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.3.1/dist/leaflet.css">
    <link href="https://fonts.googleapis.com/css?family=Roboto+Slab:700" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css?family=Open+Sans" rel="stylesheet">
    <title>{taxon_plural} Near Me</title>
    <script>
    window.NEAR_ME_CONFIG = {{
        taxon_id: {taxon_id},
        taxon_plural: {taxon_plural_json_encoded}
    }};
    </script>
    <link href="https://www.owlsnearme.com/static/css/main.c7de7c0a.css" rel="stylesheet">
</head>
<body class="home">
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
    <script type="text/javascript" src="https://www.owlsnearme.com/static/js/main.7109f461.js"></script>
</body>
</html>
'''.strip()

hostname_re = re.compile(r'^[a-z]([a-z0-9-]+)$')

COOKIE_SECRET = os.environ['COOKIE_SECRET']
CLIENT_ID = os.environ['CLIENT_ID']
CLIENT_SECRET = os.environ['CLIENT_SECRET']

# Keen
KEEN_PROJECT_ID = os.environ.get('KEEN_PROJECT_ID', None)
KEEN_WRITE_KEY = os.environ.get('KEEN_WRITE_KEY', None)

if KEEN_PROJECT_ID:
    keen.project_id = KEEN_PROJECT_ID
    keen.write_key = KEEN_WRITE_KEY


def keen_event(request, event, props=None, user=None):
    props = props or {}
    if KEEN_PROJECT_ID:
        if user:
            profile = user['profile']
            props.update({
                'uid': profile.get('uid'),
                'username': profile.get('username'),
                'email': profile.get('email'),
            })
        ip_address = request.headers.get('x-forwarded-for', '')
        user_agent = request.headers.get('user-agent', '')
        addons = []
        if ip_address:
            props['ip_address'] = ip_address
            addons.append({
                'name': 'keen:ip_to_geo',
                'input': {
                    'ip': 'ip_address'
                },
                'output': 'ip_geo_info'
            })
        if user_agent:
            props['user_agent'] = user_agent
            addons.append({
                'name': 'keen:ua_parser',
                'input': {
                    'ua_string': 'user_agent'
                },
                'output': 'parsed_user_agent'
            })
        if addons:
            props['keen'] = {
                'addons': addons
            }
        keen.add_event(event, props)


app_root = Path(__file__).parent


class UploadError(Exception):
    def __init__(self, detail):
        self.detail = detail


def upload_file(body, access_token):
    size = len(body)
    digest = hashlib.sha1(body).hexdigest()
    api_response = requests.post(
        'https://api.zeit.co/v3/now/files',
        headers={
            'Authorization': 'Bearer {}'.format(access_token),
            'Content-Type': 'application/octet-stream',
            'Content-Length': str(size),
            'x-now-digest': digest,
            'x-now-size': str(size),
        },
        data=body,
    )
    if api_response.status_code != 200:
        raise UploadError(api_response.content)
    return digest, size


def user_from_request(request):
    try:
        user = Signer(COOKIE_SECRET).unsign(
            request.cookies.get('user') or '',
        ).decode('utf8')
    except BadSignature:
        user = '{}'
    return json.loads(user)


def oauth_required(view_fn):
    @wraps(view_fn)
    def decorated_function(request, *args, **kwargs):
        user = user_from_request(request)
        if not user:
            return response.redirect('/login')
        kwargs['user'] = user
        return view_fn(request, *args, **kwargs)
    return decorated_function


class LoginView(HTTPMethodView):
    def get(self, request):
        keen_event(request, 'login_started')
        return response.redirect(
            'https://zeit.co/oauth/authorize?client_id={}'.format(CLIENT_ID)
        )


class LogoutView(HTTPMethodView):
    def get(self, request):
        keen_event(request, 'logout', user=user_from_request(request))
        r = response.redirect('/')
        del r.cookies['user']
        return r


class OuthAuthView(HTTPMethodView):
    def get(self, request):
        api_response = requests.post('https://api.zeit.co/oauth/access_token', {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'code': request.raw_args['code'],
        })
        # {"access_token":"...","token_type":"Bearer","refresh_token":"..."}
        access_token = api_response.json()['access_token']
        # Fetch their user profile
        user_profile = requests.get(
            'https://api.zeit.co/www/user',
            headers={
                'Authorization': 'Bearer {}'.format(access_token),
            }
        ).json()['user']
        d = {
            'access_token': access_token,
            'profile': user_profile,
        }
        keen_event(request, 'login_complete', user=d)
        r = response.redirect('/')
        r.cookies['user'] = Signer(COOKIE_SECRET).sign(
            json.dumps(d).encode('utf8')
        ).decode('utf8')
        return r


class IndexView(HTTPMethodView):
    def __init__(self, app):
        self.app = app

    def get(self, request):
        user = user_from_request(request)
        template = 'index.html'
        if user:
            keen_event(request, 'view_create', user=user)
            template = 'create.html'
        return response.html(
            self.app.jinja.get_template(template).render(
                profile=user and user['profile'] or None,
            )
        )


class PublishView(HTTPMethodView):
    decorators = [oauth_required]

    def __init__(self, app):
        self.app = app

    def post(self, request, user):
        taxon_id = request.json.get('taxon_id')
        taxon_plural = request.json.get('taxon_plural')
        hostname = request.json.get('hostname')
        if not isinstance(taxon_id, int):
            return response.json({
                'ok': False,
                'msg': 'taxon_id is required and must be an integer'
            })
        if not isinstance(taxon_plural, str):
            return response.json({
                'ok': False,
                'msg': 'taxon_plural is required and must be a string'
            })
        if not isinstance(hostname, str) or not hostname_re.match(hostname):
            return response.json({
                'ok': False,
                'msg': 'hostname is required and must be a valid string'
            })
        # Now build the HTML file
        html = TEMPLATE.format(
            taxon_plural=taxon_plural,
            taxon_plural_json_encoded=json.dumps(taxon_plural),
            taxon_id=taxon_id,
        )
        html_digest, html_size = upload_file(
            html.encode('utf8'), user['access_token']
        )
        # Send it to Zeit API
        deploy_body = {
            'name': hostname,
            'files': [{
                'file': 'index.html',
                'size': html_size,
                'sha': html_digest
            }],
            'deploymentType': 'STATIC',
        }
        deploy_response = requests.post(
            'https://api.zeit.co/v3/now/deployments',
            headers={
                'Authorization': 'Bearer {}'.format(user['access_token']),
                'Content-Type': 'application/json',
            },
            json=deploy_body,
        )
        if deploy_response.status_code == 200:
            reply = deploy_response.json()
            reply['deploy_url'] = reply['url']
            reply['deploy_id'] = reply['deploymentId']
            # Attempt to alias it
            intended_url = '{}.now.sh'.format(hostname)
            alias_response = requests.post(
                'https://api.zeit.co/v3/now/deployments/{}/aliases'.format(
                    reply['deploy_id'],
                ),
                headers={
                    'Authorization': 'Bearer {}'.format(user['access_token']),
                    'Content-Type': 'application/json',
                },
                json={'alias': intended_url},
            )
            if alias_response.status_code == 200:
                reply['deploy_url'] = intended_url
                reply['deploy_message'] = ''
            else:
                reply['deploy_message'] = 'Could not alias to {}'.format(
                    intended_url
                )
            reply['ok'] = True
            keen_event(request, 'publish_success', {
                'deploy_details': reply
            }, user=user)
            return response.json(reply)
        else:
            keen_event(request, 'publish_error', {
                'msg': deploy_response.content,
            }, user=user)
            return response.json({
                'ok': False,
                'msg': deploy_response.content,
            })


def build_app():
    app = Sanic(__name__)
    app.jinja = Environment(
        loader=FileSystemLoader(str(app_root / 'templates')),
        autoescape=True,
    )
    app.jinja_no_autoescape = Environment(
        loader=FileSystemLoader(str(app_root / 'templates')),
        autoescape=False,
    )
    app.static('/static/', str(app_root / 'frontend' / 'build' / 'static'))
    app.static_map = json.load(open(str(
        app_root / 'frontend' / 'build' / 'asset-manifest.json'
    )))
    app.jinja.globals['static_map'] = app.static_map
    app.add_route(IndexView.as_view(app), '/')
    app.add_route(LoginView.as_view(), '/login')
    app.add_route(LogoutView.as_view(), '/logout')
    app.add_route(OuthAuthView.as_view(), '/auth')
    app.add_route(PublishView.as_view(app), '/publish')

    app.add_route(lambda r: response.text(''), '/favicon.ico')

    # Disable Cloudflare caching entirely
    @app.middleware('response')
    async def disable_caching(request, response):
        response.headers['Cache-Control'] = 'private'

    return app


if __name__ == '__main__':
    build_app().run(
        host='0.0.0.0',
        port=8011,
        debug=bool(os.environ.get('SANIC_DEBUG', 0)),
    )
