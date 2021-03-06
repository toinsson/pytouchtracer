'''
Touch Tracer Line Drawing Demonstration
=======================================

This demonstrates tracking each touch registered to a device. You should
see a basic background image. When you press and hold the mouse, you
should see cross-hairs with the coordinates written next to them. As
you drag, it leaves a trail. Additional information, like pressure,
will be shown if they are in your device's touch.profile.

This program specifies an icon, the file icon.png, in its App subclass.
It also uses the particle.png file as the source for drawing the trails which
are white on transparent. The file touchtracer.kv describes the application.

The file android.txt is used to package the application for use with the
Kivy Launcher Android application. For Android devices, you can
copy/paste this directory into /sdcard/kivy/touchtracer on your Android device.

'''
__version__ = '1.0'

import kivy
kivy.require('1.0.6')

from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.graphics import Color, Rectangle, Point, GraphicException
from random import random
from math import sqrt


def calculate_points(x1, y1, x2, y2, steps=15):
    dx = x2 - x1
    dy = y2 - y1
    dist = sqrt(dx * dx + dy * dy)
    if dist < steps:
        return None
    o = []
    m = dist / steps
    for i in range(1, int(m)):
        mi = i / m
        lastx = x1 + dx * mi
        lasty = y1 + dy * mi
        o.extend([lastx, lasty])
    return o


class Touchtracer(FloatLayout):

    def __init__(self, pub=None, **kwargs):
        super(Touchtracer, self).__init__(**kwargs)
        self.pub = pub

    def on_motion(self, e):
        print 'on_motion ', e


    def on_touch_down(self, touch):
        print 'touch down'

        data = ",".join([str(i) for i in [touch.sx, touch.sy]])
        self.pub.send_topic("touch", "down")
        self.pub.send_topic("data", data)

        win = self.get_parent_window()
        ud = touch.ud
        ud['group'] = g = str(touch.uid)
        pointsize = 5
        if 'pressure' in touch.profile:
            ud['pressure'] = touch.pressure
            pointsize = (touch.pressure * 100000) ** 2
        ud['color'] = random()

        with self.canvas:
            Color(ud['color'], 1, 1, mode='hsv', group=g)
            ud['lines'] = [
                Rectangle(pos=(touch.x, 0), size=(1, win.height), group=g),
                Rectangle(pos=(0, touch.y), size=(win.width, 1), group=g),
                Point(points=(touch.x, touch.y), source='particle.png',
                      pointsize=pointsize, group=g)]

        ud['label'] = Label(size_hint=(None, None))
        self.update_touch_label(ud['label'], touch)
        self.add_widget(ud['label'])
        touch.grab(self)
        return True

    def on_touch_move(self, touch):

        if touch.grab_current is not self:
            return
        ud = touch.ud
        ud['lines'][0].pos = touch.x, 0
        ud['lines'][1].pos = 0, touch.y

        index = -1

        while True:
            try:
                points = ud['lines'][index].points
                oldx, oldy = points[-2], points[-1]
                break
            except:
                index -= 1

        points = calculate_points(oldx, oldy, touch.x, touch.y, steps=5)

        # if pressure changed create a new point instruction
        if 'pressure' in ud:
            if not .95 < (touch.pressure / ud['pressure']) < 1.05:
                g = ud['group']
                pointsize = (touch.pressure * 100000) ** 2
                with self.canvas:
                    Color(ud['color'], 1, 1, mode='hsv', group=g)
                    ud['lines'].append(
                        Point(points=(), source='particle.png',
                              pointsize=pointsize, group=g))

        if points:
            data = ",".join([str(i) for i in [touch.sx, touch.sy]])
            self.pub.send_topic("touch", "move")
            self.pub.send_topic("data", data)
            print 'touch move ', data

            try:
                lp = ud['lines'][-1].add_point
                for idx in range(0, len(points), 2):
                    lp(points[idx], points[idx + 1])
            except GraphicException:
                pass

        ud['label'].pos = touch.pos
        import time
        t = int(time.time())
        if t not in ud:
            ud[t] = 1
        else:
            ud[t] += 1
        self.update_touch_label(ud['label'], touch)

    def on_touch_up(self, touch):
        print 'touch up'

        data = ",".join([str(i) for i in [touch.sx, touch.sy]])
        self.pub.send_topic("touch", "up")
        self.pub.send_topic("data", data)

        if touch.grab_current is not self:
            return
        touch.ungrab(self)
        ud = touch.ud
        self.canvas.remove_group(ud['group'])
        self.remove_widget(ud['label'])

    def update_touch_label(self, label, touch):
        label.text = 'ID: %s\nPos: (%d, %d)\nClass: %s' % (
            touch.id, touch.x, touch.y, touch.__class__.__name__)
        label.texture_update()
        label.pos = touch.pos
        label.size = label.texture_size[0] + 20, label.texture_size[1] + 20

from kivy.core.window import Window

import clientserver as cs



def print_prop(*args):
    print args

class TouchtracerApp(App):
    title = 'Touchtracer'
    icon = 'icon.png'

    def build(self):

        self.pub = cs.SimplePublisher(port = "5556")
        tc = Touchtracer(pub = self.pub)

        # callbacks for the window
        def print_enter(*args):
            self.pub.send_topic("hover", "enter")
            self.pub.send_topic("data", "0,0")
            print 'enter ', args
        def print_mouse_pos(e,f):
            self.pub.send_topic("hover", "move")
            # self.pub.send_topic("data", ",".join([str(i) for i in f]))
            data = str(f[0]/e.width) +","+ str(f[1]/e.height)
            self.pub.send_topic("data", data)
            print data
        def print_leave(*args):
            self.pub.send_topic("hover", "exit")
            self.pub.send_topic("data", "0,0")
            print 'leave ', args

        # watch over the mouse_pos
        Window.bind(mouse_pos=print_mouse_pos)
        # Window.bind(focus=print_prop)
        Window.bind(on_cursor_enter=print_enter)
        Window.bind(on_cursor_leave=print_leave)

        return tc

    def on_pause(self):
        return True

    def on_stop(self):
        self.pub.close()

if __name__ == '__main__':
    TouchtracerApp().run()
