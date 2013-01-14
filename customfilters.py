#!/usr/bin/env python

import re
from google.appengine.ext import webapp

register = webapp.template.create_template_register()
 
# Override Django's urlize here
def urlize(url):
    try:
        html = """<a href="%s%s%s">%s</a>"""
        s = re.search(r'(.*://)?([^/]+)(.*)', url)
        if s.group(1) == 'https://':
            prefix = 'https://'
        else:
            prefix = 'http://'
        return html % (prefix, s.group(2), s.group(3), s.group(2))
    except:
        return url
 
register.filter(urlize)
