#!/usr/bin/env python

import re
from google.appengine.ext import webapp

register = webapp.template.create_template_register()
 
# Override Django's urlize here
def urlize(url):
    try:
        html = """%s"""
        s = re.search(r'(.*://)?([^/]+)(.*)', url)
        return html % (s.group(2))
    except:
        return url
 
register.filter(urlize)
