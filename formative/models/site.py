from django.db import models
from django.db.models import UniqueConstraint, Q
from django.contrib import auth, sites


class Site(sites.models.Site):
    time_zone = models.CharField(max_length=32, blank=True)


class User(auth.models.AbstractUser):
    class Meta:
        constraints = [
            UniqueConstraint(fields=['site', 'email'], name='uniq_site_email'),
        ]
        ordering = ['site', 'email']
    
    site = models.ForeignKey(Site, models.CASCADE, null=True, blank=True,
                             related_name='users', related_query_name='user')
    programs = models.ManyToManyField('Program', blank=True,
                                      related_name='users',
                                      related_query_name='user')
