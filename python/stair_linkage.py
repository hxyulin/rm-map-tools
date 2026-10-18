# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""DreamChaser source-fit closure; matches physics::mechanism::ClimbingConfig."""
import numpy as np

BODY_SOURCE_M = np.array([.0012495569289, .080, .3308321676576])
TRAVEL_RAD = .0926526307467
DEPLOYED_RAD = 1.3302776523948
C = np.array([[0,0,1],[1,0,0],[0,1,0.]])


def frames(input_rad):
    """Native-GLB body-relative rigid frames; all links close analytically."""
    theta = TRAVEL_RAD + input_rad
    a = np.array([.215, 0., -.0152747187334])
    d = np.array([-.135, 0., -.1452747187334])
    direction = np.array([-np.sin(theta), 0., -np.cos(theta)])
    b = a + .130 * direction
    c = np.array([b[0]-np.sqrt(.200**2-(b[2]+.0252747187334)**2), 0., -.0252747187334])
    rear = (d-c)/np.linalg.norm(d-c)
    beta = np.arctan2(-rear[0], -rear[2])
    gamma = np.arctan2(-(c-b)[0], -(c-b)[2])
    def pose(origin, angle):
        cos, sin = np.cos(angle), np.sin(angle)
        result = np.eye(4)
        result[:3,:3] = C.T @ np.array([[cos,0,sin],[0,1,0],[-sin,0,cos]]) @ C
        result[:3,3] = C.T @ origin
        return result
    result = {'body':np.eye(4), 'front':pose(a,theta), 'coupler':pose(b,gamma),
              'rear':pose(c,beta), 'guide':pose(d,beta), 'slider':pose(c,0.)}
    hubs = [a + .190*direction, c + .320*rear]
    for i in range(4):
        p = hubs[i//2].copy();p[1]=[.2083,-.2083][i%2]
        result[f'wheel-{i}'] = pose(p,0.)
    return result


# Audited leaf ordinals under 1/1/1. Bearings at fixed frame hinges remain body.
FRONT = set(range(55,70)) | set(range(74,88)) | {123,124,125,128,129} | {144,145,150,151,152,153} | set(range(156,167))
COUPLER = {1,2,3,4,5,6,7,8,9,25,26,115,116,117,118,119,120,122,136,137,138,139}
SLIDER = {11,12,18,19,20,21,22,23,24,106,111,112,113,114,140,141,142,143}
GUIDE = {13,16,27,28,29,30} | set(range(45,55)) | set(range(88,98)) | {104,105,107,110,126,127,167,168,169,170}
REAR = {10,14,15,17} | set(range(33,45)) | set(range(98,104)) | {108,109,121,146,147,148,149,154,155}
WHEELS = {32:'wheel-0',131:'wheel-1',31:'wheel-2',130:'wheel-3'}


def group(path):
    """Assign source parts once; auxiliary sensor linkages remain unactuated."""
    if path.startswith('1/1/1/'):
        part=int(path.split('/')[3])
        if part in WHEELS:return WHEELS[part]
        for indices, name in [(FRONT,'front'),(COUPLER,'coupler'),(SLIDER,'slider'),(GUIDE,'guide'),(REAR,'rear')]:
            if part in indices:return name
    if path in ('1/1/3','1/1/7','1/1/12','1/1/13','1/1/51','1/1/52'):
        return 'slider'
    return 'body'
