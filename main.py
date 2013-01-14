#!/usr/bin/env python
#
#  Copyright 2010 Matthew Smith. All rights reserved.
#  
#  Redistribution and use in source and binary forms, with or without modification, are
#  permitted provided that the following conditions are met:
#  
#     1. Redistributions of source code must retain the above copyright notice, this list of
#        conditions and the following disclaimer.
#  
#     2. Redistributions in binary form must reproduce the above copyright notice, this list
#        of conditions and the following disclaimer in the documentation and/or other materials
#        provided with the distribution.
#  
#  THIS SOFTWARE IS PROVIDED BY MATTHEW SMITH ``AS IS'' AND ANY EXPRESS OR IMPLIED
#  WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
#  FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> OR
#  CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#  SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
#  ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
#  ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#  
#  The views and conclusions contained in the software and documentation are those of the
#  authors and should not be interpreted as representing official policies, either expressed
#  or implied, of Matthew Smith.
#
#  Matthew Smith <mbenjaminsmith@gmail.com>

from datetime import datetime, timedelta
from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util, template
from google.appengine.api import users, memcache

webapp.template.register_template_library('customfilters')

class UserMeta(db.Model):
  user = db.UserProperty()
  points = db.IntegerProperty(indexed=True, default=1)
  date = db.DateTimeProperty(auto_now_add=True)

class BaseItem(db.Model):
  user = db.UserProperty(indexed=True)
  points = db.IntegerProperty(indexed=True, default=1)
  upvotes = db.ListProperty(str, indexed=False)
  date = db.DateTimeProperty(auto_now_add=True)

class Post(BaseItem):
  title = db.StringProperty(indexed=True, default='')
  url = db.StringProperty(indexed=True, default='')
  text = db.TextProperty(default='')
  
class Comment(BaseItem):
  postid = db.IntegerProperty(indexed=True)
  parentid = db.IntegerProperty(indexed=False, default=0)
  depth = db.IntegerProperty(indexed=False, default=0)
  text = db.TextProperty(default='')

def requirelogin(fn):
  def __requirelogin(self, *args, **kwargs):
    user = users.get_current_user()
    if user is None:
      return self.redirect(users.create_login_url(self.request.uri))
    else:
      return fn(self, *args, **kwargs)
  return __requirelogin

def rank(model):
  delta = datetime.now() - model.date
  hours = (delta.days * 24) + (delta.seconds / 3600)
  rank = (model.points - 1) / ((hours + 2) ** 1.5)
  return rank
  
class BaseHandler(webapp.RequestHandler):
  def render(self, html, args):
    username, usermeta = None, None
    user = users.get_current_user()
    if user:
      username = user.nickname()
      usermeta = memcache.get(user.__str__())
      if usermeta is None:
        usermeta = UserMeta.all().filter('user = ', user).get()
        if usermeta is None:
          usermeta = UserMeta(user=user)
          usermeta.put()
        memcache.set(user.__str__(), usermeta)
    full_args = dict(args, **{
      'user': username,
      'usermeta': usermeta,
      'login': users.create_login_url(self.request.uri),
      'logout': users.create_logout_url('/')
    })
    self.response.out.write(template.render('templates/%s' % html, full_args))

class MainHandler(BaseHandler):
  def get(self):
    if self.request.path.startswith('/newest'):
      posts = memcache.get('posts-newest')
      if posts is None:
        posts = Post.all().order('-date').fetch(100)
        memcache.set('posts-newest', posts)
    else:
      posts = memcache.get('posts-ranked')
      if posts is None:
        posts = Post.all().order('-date').fetch(200)
        tosort = [(rank(p), p.date, p) for p in posts]
        tosort.sort()
        tosort.reverse()
        posts = [p for _, _, p in tosort]
        memcache.set('posts-ranked', posts, 600)
    for post in posts:
      post.nickname = post.user.nickname()
      post.id = post.key().id()
      
    self.render('index.html', {
      'posts': posts
    })
    
class ItemHandler(BaseHandler):
  def get(self, id=''):
    if id:
      item = Post.get_by_id(int(id))
    else:
      return self.redirect('/')
    if item:
      item.nickname = item.user.nickname()
      item.id = item.key().id()
    threaded = memcache.get('comments-%s' % item.id)
    threaded = None
    if threaded is None:
      comments = Comment.all().filter('postid = ', item.id).fetch(1000)
      threaded, children = [], []
      for comment in comments:
        comment.nickname = comment.user.nickname()
        comment.id = comment.key().id()
        if comment.parentid == 0:
          threaded.append(comment)
        else:
          children.append(comment)
      tosort = [(rank(c), c.date, c) for c in threaded]
      tosort.sort()
      tosort.reverse()
      threaded = [c for _, _, c in tosort]
      tosort = [(c.date, c) for c in children]
      tosort.sort()
      #tosort.reverse()
      children = [c for _, c in tosort]
      for comment in children:
        i = 0
        parents = list(threaded)
        for parent in parents:
          if parent.key().id() == comment.parentid:
            threaded.insert(1 + i, comment)
            i = i + 2
          else:
            i = i + 1
        # Indent
        comment.depth = comment.depth * 2
      memcache.set('comments-%s' % item.id, threaded)
    self.render('item.html', {
      'item': item,
      'threaded': threaded
    })
    
class PostHandler(BaseHandler):
  @requirelogin
  def get(self, id='', delete=''):
    if id:
      data = Post.get_by_id(int(id))
      if delete == 'delete':
        user = users.get_current_user()
        if data.user == user:
          data.delete()
          memcache.delete_multi(['posts-newest', 'posts-ranked'])
          return self.redirect('/')
    else:
      data = None
    self.render('post.html', {
      'data': data,
      'id': id
    })
  @requirelogin
  def post(self, *args):
    id = self.request.get('id')
    if id != '':
      data = Post.get_by_id(int(id))
    else:
      data = Post()
    user = users.get_current_user()
    data.user = user
    data.title = self.request.get('title')
    data.url = self.request.get('url')
    data.text = self.request.get('text')
    data.points = 1
    data.upvotes.append(user.__str__())
    data.put()
    memcache.delete_multi(['posts-newest', 'posts-ranked'])
    return self.redirect('/newest')

class CommentHandler(BaseHandler):
  @requirelogin
  def get(self, postid, parentid, depth, id, delete):
    comment, parent = None, None
    if parentid != '' and parentid != '0':
      parent = Comment.get_by_id(int(parentid))
    else:
      parentid = 0
    if id:
      comment = Comment.get_by_id(int(id))
      if delete == 'delete':
        user = users.get_current_user()
        if comment.user == user:
          comment.delete()
          return self.redirect('/item/%s' % postid)
      postid = comment.postid
      parentid = comment.parentid
      depth = comment.depth
    self.render('comment.html', {
      'comment': comment,
      'parent': parent,
      'postid': postid,
      'parentid': parentid,
      'depth': depth,
      'id': id
    })
  @requirelogin
  def post(self, postid, parentid, depth, id, delete):
    if id != '':
      comment = Comment.get_by_id(int(id))
    else:
      comment = Comment()
    if comment:
      comment.user = users.get_current_user()
      comment.text = self.request.get('text')
      comment.postid = int(postid)
      if parentid != '':
        comment.parentid = int(parentid)
      if depth != '':
        comment.depth = int(depth)
      comment.put()
      memcache.delete('comments-%s' % postid)
      return self.redirect('/item/%s' % postid)
          
class VoteHandler(BaseHandler):
  @requirelogin
  def get(self, dir, model, id):
    if id != '':
      if model == 'post':
        item = Post.get_by_id(int(id))
      if model == 'comm':
        item = Comment.get_by_id(int(id))
    if item:
      user = users.get_current_user().__str__()
      if dir == 'up':
        if user not in item.upvotes:
          item.points = item.points + 1
          item.upvotes.append(user)
          item.put()
          usermeta = UserMeta.all().filter('user = ', users.get_current_user()).get()
          usermeta.points = usermeta.points + 1
          usermeta.put()
          memcache.delete_multi(['posts-newest', 'posts-ranked', user])
          return self.response.out.write(item.points)
      
def main():
  application = webapp.WSGIApplication([
    ('/(up|down)vote/(post|comm)/(\d*)', VoteHandler),
    ('/post/?(\d*)/?(delete)?', PostHandler),
    ('/comment/(\d+)/?(\d*)/?(\d*)/?(?:id)?/?(\d*)/?(delete)?', CommentHandler),
    ('/item/(\d+)', ItemHandler),
    ('/newest', MainHandler),
    ('/', MainHandler)],
    debug=False)
  util.run_wsgi_app(application)

if __name__ == '__main__':
  main()
