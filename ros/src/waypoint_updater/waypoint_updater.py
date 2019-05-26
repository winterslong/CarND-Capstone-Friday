#!/usr/bin/env python

import rospy
from geometry_msgs.msg import PoseStamped
from styx_msgs.msg import Lane, Waypoint
from std_msgs.msg import Int32
from scipy.spatial import KDTree
import numpy as np
import time
import thread

import math

'''
This node will publish waypoints from the car's current position to some `x` distance ahead.

As mentioned in the doc, you should ideally first implement a version which does not care
about traffic lights or obstacles.

Once you have created dbw_node, you will update this node to use the status of traffic lights too.

Please note that our simulator also provides the exact location of traffic lights and their
current status in `/vehicle/traffic_lights` message. You can use this message to build this node
as well as to verify your TL classifier.

TODO (for Yousuf and Aaron): Stopline location for each traffic light.
'''

LOOKAHEAD_WPS = 50 # Number of waypoints we will publish. You can change this number
CONSTANT_DECEL = 1 / LOOKAHEAD_WPS  # Deceleration constant for smoother braking
PUBLISHING_RATE = 20  # Rate (Hz) of waypoint publishing
STOP_LINE_MARGIN = 2  # Distance in waypoints to pad in front of the stop line
MAX_DECL = 0.5


class WaypointUpdater(object):
    def __init__(self):
        rospy.init_node('waypoint_updater', log_level=rospy.INFO)
        rospy.loginfo("Welcome to waypoint_updater")

        # TODO: Add other member variables you need below
        self.pose = None
        self.base_waypoints = None
        self.stopline_wp_idx = -1
        self.waypoints_2d = None
        self.waypoint_tree = None
        self.thread_working = False

        self.waypoint_delay_time = 0
        self.pose_delay_time = 0

        rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb)
        rospy.Subscriber('/base_waypoints', Lane, self.base_waypoints_cb)

        # TODO: Add a subscriber for /traffic_waypoint and /obstacle_waypoint below
        rospy.Subscriber('/traffic_waypoint', Int32, self.traffic_cb)
        
        self.final_waypoints_pub = rospy.Publisher('final_waypoints', Lane, queue_size=1)

        rospy.spin()
        #self.loop()

    def loop(self):
        rate = rospy.Rate(5)
        while not rospy.is_shutdown():
            if self.pose and self.base_waypoints:
                self.publish_waypoints()
            rate.sleep()
    
    def get_closest_waypoint_id(self):
        x = self.pose.pose.position.x
        y = self.pose.pose.position.y
        closest_idx = self.waypoint_tree.query([x,y],1)[1]

        closest_coord = self.waypoints_2d[closest_idx]
        prev_coord = self.waypoints_2d[closest_idx-1]

        cl_vect = np.array(closest_coord)
        prev_vect = np.array(prev_coord)
        pos_vect = np.array([x, y])

        val = np.dot(cl_vect-prev_vect, pos_vect-cl_vect)

        if val > 0:
            closest_idx = (closest_idx + 1) % len(self.waypoints_2d)
        return closest_idx

    def publish_waypoints(self):
        start_t = time.time()

        final_wp = self.generate_wp()
        self.final_waypoints_pub.publish(final_wp)

        current_time = time.time()
        rospy.logdebug("Waypoint delay time:%.4f s", current_time - self.waypoint_delay_time)

        self.thread_working = False

    def generate_wp(self):
        lane = Lane()

        closest_wp_idx = self.get_closest_waypoint_id()
        farthest_wp_idx = closest_wp_idx + LOOKAHEAD_WPS
        base_wp = self.base_waypoints.waypoints[closest_wp_idx:farthest_wp_idx]

        if self.stopline_wp_idx == -1 or self.stopline_wp_idx >= farthest_wp_idx:
            lane.waypoints = base_wp
        else:
            lane.waypoints = self.decelerate_waypoints(base_wp, closest_wp_idx)
        
        return lane

    def decelerate_waypoints(self,waypoints, closest_idx):
        decl_wp = []
        for i in range(len(waypoints)):
            p = Waypoint()
            p.pose = waypoints[i].pose

            stop_idx = max(self.stopline_wp_idx - closest_idx - STOP_LINE_MARGIN, 0)
            dist = self.distance(waypoints, i, stop_idx)
            vel = math.sqrt(2 * MAX_DECL * dist) + (i * CONSTANT_DECEL)
            if vel < 2.0:
                vel = 0
            
            p.twist.twist.linear.x = min(vel, waypoints[i].twist.twist.linear.x)
            decl_wp.append(p)
        
        return decl_wp

    def pose_cb(self, msg):
        # TODO: Implement
        current_time = time.time()
        rospy.logdebug("Pose update time:%.4f s", current_time - self.pose_delay_time)
        self.pose_delay_time = current_time
        
        self.pose = msg
        if not self.thread_working:
            if self.base_waypoints:

                self.thread_working = True
                self.waypoint_delay_time = time.time()
                thread.start_new_thread( self.publish_waypoints, ())
        else:
            pass
                

        current_time = time.time()
        
        self.last_pose_time = current_time


    def base_waypoints_cb(self, waypoints):
        # TODO: Implement
        rospy.loginfo("Base waypoint Callback")
        self.base_waypoints = waypoints
        if not self.waypoints_2d:
            self.waypoints_2d = [[waypoint.pose.pose.position.x, waypoint.pose.pose.position.y] for waypoint in waypoints.waypoints]
            self.waypoint_tree = KDTree(self.waypoints_2d)


    def traffic_cb(self, msg):
        # TODO: Callback for /traffic_waypoint message. Implement
        if self.stopline_wp_idx != msg.data:
            rospy.logwarn("[Waypoint Updater] stopline_wp_idx updated: %s.", msg.data)

        self.stopline_wp_idx = msg.data

    def obstacle_cb(self, msg):
        # TODO: Callback for /obstacle_waypoint message. We will implement it later
        pass

    def get_waypoint_velocity(self, waypoint):
        return waypoint.twist.twist.linear.x

    def set_waypoint_velocity(self, waypoints, waypoint, velocity):
        waypoints[waypoint].twist.twist.linear.x = velocity

    def distance(self, waypoints, wp1, wp2):
        dist = 0
        dl = lambda a, b: math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2  + (a.z-b.z)**2)
        for i in range(wp1, wp2+1):
            dist += dl(waypoints[wp1].pose.pose.position, waypoints[i].pose.pose.position)
            wp1 = i
        return dist


if __name__ == '__main__':
    try:
        WaypointUpdater()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start waypoint updater node.')
