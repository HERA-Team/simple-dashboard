import matplotlib
matplotlib.use('PS')
import matplotlib.pyplot as plt
import numpy as np
import healpy
import os
import sys
import astropy.coordinates
from astropy import units as u
from astropy.io import fits
from astropy.utils.data import get_pkg_data_filename
from astropy.time import Time
from datetime import datetime, timedelta

#file can be retrived by running !wget http://danielcjacobs.com/uploads/test4.fits
mappy = healpy.read_map('test4.fits')

def get_map():
    #Get current time 
    now = Time.now()
    T = datetime.utcnow() + timedelta(hours = 0)
    T  = Time(T, format = 'datetime')
    loc = astropy.coordinates.EarthLocation(lon =  22.13303, lat = -31.58)
    print(T)
    
    ra = (T.sidereal_time('mean', longitude =  22.13303))/u.hourangle
    lon = (ra*15-360)
    rot = [(lon), -31.58]
    
    moon = astropy.coordinates.get_moon(T, location = loc, ephemeris=None)
    sun = astropy.coordinates.get_sun(T)
    
    ssbodies = ['mercury', 'venus', 'mars', 'jupiter', 'saturn', 'neptune', 'uranus']
    colors = ['grey', 'pink', 'red', 'orange', 'yellow', 'blue', 'blue', 'blue']
        
    pic = astropy.coordinates.SkyCoord(ra = '05h19m49.7230919028', dec = '-45d 46m 44s') #Pictor
    forn = astropy.coordinates.SkyCoord(ra = '03h23m25.1s', dec = '-37d 08m')
    cass = astropy.coordinates.SkyCoord(ra = '23h 23m 24s', dec = '+58d 48.9m')
    crab = astropy.coordinates.SkyCoord(ra = '05h 34m 31s', dec = '+22d 00m 52.2s')
    lmc =  astropy.coordinates.SkyCoord(ra = '05h 40m 05s', dec = '-69d 45m 51s')
    smc =  astropy.coordinates.SkyCoord(ra = '00h 52m 44.8s', dec = '-72d 49m 43s')
    cenA = astropy.coordinates.SkyCoord(ra = '13h 25m 27.6s', dec = '-43d 01m 09s')
    callibrator1 =  astropy.coordinates.SkyCoord(ra = 109.32351*u.degree, dec = -25.0817*u.degree)
    callibrator2 = astropy.coordinates.SkyCoord(ra = 30.05044*u.degree, dec = -30.89106*u.degree)
    callibrator3 = astropy.coordinates.SkyCoord(ra = 6.45484*u.degree, dec = -26.0363*u.degree) 
                                           
    source_list = [[moon, 'moon', 'slategrey'], [sun, 'sun', 'y'], [pic, 'pictor', 'w'], [forn, 'fornax', 'w'], [cass, 'Cass A', 'w'], [crab, 'Crab', 'w'], 
                   [lmc, 'LMC', 'w'], [cenA, 'Cen A', 'w'], [smc, 'SMC', 'w'], [callibrator1, 'J071717.6-250454', 'r'], [callibrator2, 'J020012.1-305327', 'r'], [callibrator3, ' J002549.1-260210', 'r']]
    
    healpy.orthview(np.log10(mappy), coord = ['G', 'C'], rot = rot, return_projected_map = True, min = 0, max = 2, half_sky = 1)
    
    
    for item in source_list:
        if item[1] == 'sun':
            name = item[1] 
            healpy.projscatter(item[0].ra, item[0].dec, lonlat = True, s = 1000, c = item[2], label = name)
            healpy.projtext(item[0].ra, item[0].dec,  lonlat = True, color = 'k', s =  name)  
        if item[1] == 'moon':
            name = item[1] 
            healpy.projscatter(item[0].ra, item[0].dec, lonlat = True, s = 200, c = item[2], label = name)
            healpy.projtext(item[0].ra, item[0].dec,  lonlat = True, color = 'k', s =  name)  
        else:
            name = item[1] 
            healpy.projscatter(item[0].ra, item[0].dec, lonlat = True, s = 50, color = item[2], label = name)
            healpy.projtext(item[0].ra, item[0].dec,  lonlat = True, color = 'k', s =  name)  
        
    count = 0
    for body in ssbodies:
        name = body
        body = astropy.coordinates.get_body(body, T) 
        healpy.projscatter(body.ra, body.dec, lonlat = True, s = 50, color = colors[count], label = name)
        healpy.projtext(body.ra, body.dec,  lonlat = True, color = 'k', s = name) 
        count += 1
       
    
get_map()
plt.savefig('out.png')
