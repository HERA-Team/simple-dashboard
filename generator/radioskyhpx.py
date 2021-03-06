# coding: utf-8

# In[1]:


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


# In[2]:


# file can be retrived by running !wget http://danielcjacobs.com/uploads/test4.fits
mappy = healpy.read_map("test4.fits")


# In[21]:


def get_map():
    # Get current time
    now = Time.now()
    sidereal = now.sidereal_time("mean", longitude=22.13303)
    loc = astropy.coordinates.EarthLocation(lon=22.13303, lat=-31.58)
    T = Time(now, format="datetime", location=loc)
    # T = Time('2019-07-23 15:46:30', scale='utc', location = loc)
    print(T)

    ra = (now.sidereal_time("mean", longitude=22.13303)) / u.hourangle
    dec = -31.58
    rot = [-112.13, -31.06]

    moon = astropy.coordinates.get_moon(T, location=loc, ephemeris=None)
    sun = astropy.coordinates.get_sun(T)

    ssbodies = ["mercury", "venus", "mars", "jupiter", "saturn", "neptune", "uranus"]
    colors = ["grey", "pink", "red", "orange", "yellow", "blue", "blue", "blue"]

    pic = astropy.coordinates.SkyCoord(
        ra="05h19m49.7230919028", dec="−45° 46′ 44″"
    )  # Pictor
    forn = astropy.coordinates.SkyCoord(ra="03h23m25.1s", dec="-37° 08")
    cass = astropy.coordinates.SkyCoord(ra="23h 23m 24s", dec="+58° 48.9′")
    crab = astropy.coordinates.SkyCoord(ra="05h 34m 31s", dec="+22° 00′ 52.2″")
    lmc = astropy.coordinates.SkyCoord(ra="05h 40m 05s", dec="−69° 45′ 51″")
    smc = astropy.coordinates.SkyCoord(ra="00h 52m 44.8s", dec="−72° 49′ 43″")
    cenA = astropy.coordinates.SkyCoord(ra="13h 25m 27.6s", dec="−43° 01′ 09″")
    callibrator1 = astropy.coordinates.SkyCoord(
        ra=109.32351 * u.degree, dec=-25.0817 * u.degree
    )
    callibrator2 = astropy.coordinates.SkyCoord(
        ra=30.05044 * u.degree, dec=-30.89106 * u.degree
    )
    callibrator3 = astropy.coordinates.SkyCoord(
        ra=6.45484 * u.degree, dec=-26.0363 * u.degree
    )

    source_list = [
        [moon, "moon", "slategrey"],
        [sun, "sun", "y"],
        [pic, "pictor", "w"],
        [forn, "fornax", "w"],
        [cass, "Cass A", "w"],
        [crab, "Crab", "w"],
        [lmc, "LMC", "w"],
        [cenA, "Cen A", "w"],
        [smc, "SMC", "w"],
        [callibrator1, "J071717.6-250454", "r"],
        [callibrator2, "J020012.1-305327", "r"],
        [callibrator3, " J002549.1-260210", "r"],
    ]

    healpy.orthview(
        np.log10(mappy),
        coord=["G", "C"],
        rot=rot,
        return_projected_map=True,
        max=2,
        half_sky=0,
    )

    for item in source_list:
        if item[1] == "sun":
            name = item[1]
            healpy.projscatter(
                item[0].ra, item[0].dec, lonlat=True, s=1000, c=item[2], label=name
            )
            healpy.projtext(item[0].ra, item[0].dec, lonlat=True, c="k", s=name)
        if item[1] == "moon":
            name = item[1]
            healpy.projscatter(
                item[0].ra, item[0].dec, lonlat=True, s=200, c=item[2], label=name
            )
            healpy.projtext(item[0].ra, item[0].dec, lonlat=True, c="k", s=name)
        else:
            name = item[1]
            healpy.projscatter(
                item[0].ra, item[0].dec, lonlat=True, s=50, c=item[2], label=name
            )
            healpy.projtext(item[0].ra, item[0].dec, lonlat=True, c="k", s=name)

    count = 0
    for body in ssbodies:
        name = body
        body = astropy.coordinates.get_body(body, T)
        healpy.projscatter(
            body.ra, body.dec, lonlat=True, s=50, c=colors[count], label=name
        )
        healpy.projtext(body.ra, body.dec, lonlat=True, c="k", s=name)
        count += 1


get_map()
plt.savefig("out.png")
