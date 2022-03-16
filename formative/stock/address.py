from django.core.exceptions import ValidationError
from django.db import models
from localflavor.us import forms as us_forms

from . import CompositeStockWidget


class AddressWidget(CompositeStockWidget):
    TYPE = 'address'
    
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        
        self.template_name = 'address.html'
        self.review_template_name = 'address_review.html'
        
        self.labels = {
            'street_address': 'Street address',
            'city': 'City',
            'state': 'State',
            'postal_code': 'Zip/postal code',
            'country': 'Country'
        }
    
    def fields(self):
        ret = []
        for name in ('street_address', 'city', 'state', 'postal_code',
                      'country'):
            length = 32
            if name == 'street_address': length = 64
            elif name == 'postal_code': length = 16
            
            f = self.field_name(name)
            if name != 'country':
                ret.append((f, models.CharField(max_length=length, blank=True)))
            else:
                ret.append((f, models.CharField(max_length=2, default='US',
                                                choices=COUNTRIES)))
        return ret
    
    def field_required(self, part):
        if not super().field_required(part): return False
        if part in ('street_address', 'city', 'country'): return True
        return False

    def clean(self, data):
        if data['country'] == 'US':
            for name, us_field in (('state', 'USStateField'),
                                   ('postal_code', 'USZipCodeField')):
                if not data[name]:
                    return {name: ValidationError('This field is required.')}
                else:
                    try:
                        val = getattr(us_forms, us_field)().clean(data[name])
                    except ValidationError as e:
                        return { name: e }
                    else:
                        data[name] = val
        return data
    
    def render_choices(self):
        return [('city', 'city, state and country'),
                ('state', 'state and country'), ('country', 'country')]
    
    def render(self, choice, **kwargs):
        vals = [kwargs['country']]
        if choice in ('city', 'state'): vals.insert(0, kwargs['state'])
        if choice == 'city': vals.insert(0, kwargs['city'])
        return ', '.join([ v for v in vals if v ])


COUNTRIES = (
    ('US', 'United States'),
    ('--', '-------------'),
    ('AF', 'Afghanistan'), 
    ('AX', 'Aland Islands'),
    ('AL', 'Albania'), 
    ('DZ', 'Algeria'), 
    ('AS', 'American Samoa'),
    ('AD', 'Andorra'), 
    ('AO', 'Angola'), 
    ('AI', 'Anguilla'), 
    ('AG', 'Antigua and Barbuda'), 
    ('AR', 'Argentina'), 
    ('AM', 'Armenia'), 
    ('AW', 'Aruba'), 
    ('AU', 'Australia'), 
    ('AT', 'Austria'), 
    ('AZ', 'Azerbaijan'), 
    ('BS', 'Bahamas (the)'), 
    ('BH', 'Bahrain'), 
    ('BD', 'Bangladesh'), 
    ('BB', 'Barbados'), 
    ('BY', 'Belarus'), 
    ('BE', 'Belgium'), 
    ('BZ', 'Belize'), 
    ('BJ', 'Benin'), 
    ('BM', 'Bermuda'), 
    ('BT', 'Bhutan'), 
    ('BO', 'Bolivia (Plurinational State of)'), 
    ('BQ', 'Bonaire, Sint Eustatius and Saba'),
    ('BA', 'Bosnia and Herzegovina'), 
    ('BW', 'Botswana'), 
    ('BR', 'Brazil'), 
    ('BN', 'Brunei Darussalam'), 
    ('BG', 'Bulgaria'), 
    ('BF', 'Burkina Faso'), 
    ('BI', 'Burundi'), 
    ('CV', 'Cabo Verde'), 
    ('KH', 'Cambodia'), 
    ('CM', 'Cameroon'), 
    ('CA', 'Canada'), 
    ('KY', 'Cayman Islands (the)'), 
    ('CF', 'Central African Republic (the)'), 
    ('TD', 'Chad'), 
    ('CL', 'Chile'), 
    ('CN', 'China'), 
    ('CX', 'Christmas Island'),
    ('CC', 'Cocos (Keeling) Islands (the)'),
    ('CO', 'Colombia'), 
    ('KM', 'Comoros'), 
    ('CG', 'Congo (the)'), 
    ('CD', 'Congo (the Democratic Republic of the)'),
    ('CK', 'Cook Islands (the)'),
    ('CR', 'Costa Rica'), 
    ('CI', 'Cote d\'Ivoire'), 
    ('HR', 'Croatia'), 
    ('CU', 'Cuba'), 
    ('CW', 'Curacao'),
    ('CY', 'Cyprus'), 
    ('CZ', 'Czechia'),
    ('DK', 'Denmark'), 
    ('DJ', 'Djibouti'), 
    ('DM', 'Dominica'), 
    ('DO', 'Dominican Republic'), 
    ('EC', 'Ecuador'), 
    ('EG', 'Egypt'), 
    ('SV', 'El Salvador'), 
    ('GQ', 'Equatorial Guinea'), 
    ('ER', 'Eritrea'), 
    ('EE', 'Estonia'), 
    ('SZ', 'Eswatini'), 
    ('ET', 'Ethiopia'), 
    ('FK', 'Falkland Islands (the)'), 
    ('FO', 'Faroe Islands (the)'), 
    ('FJ', 'Fiji'), 
    ('FI', 'Finland'), 
    ('FR', 'France'), 
    ('GF', 'French Guiana'), 
    ('PF', 'French Polynesia'), 
    ('GA', 'Gabon'), 
    ('GM', 'Gambia (the)'), 
    ('GE', 'Georgia'), 
    ('DE', 'Germany'), 
    ('GH', 'Ghana'), 
    ('GI', 'Gibraltar'),
    ('GR', 'Greece'), 
    ('GL', 'Greenland'), 
    ('GD', 'Grenada'), 
    ('GP', 'Guadeloupe'), 
    ('GT', 'Guatemala'), 
    ('GG', 'Guernsey'),
    ('GN', 'Guinea'), 
    ('GW', 'Guinea-Bissau'), 
    ('GY', 'Guyana'), 
    ('HT', 'Haiti'), 
    ('VA', 'Holy See'), 
    ('HN', 'Honduras'), 
    ('HK', 'Hong Kong'), 
    ('HU', 'Hungary'), 
    ('IS', 'Iceland'), 
    ('IN', 'India'), 
    ('ID', 'Indonesia'), 
    ('IR', 'Iran (Islamic Republic of)'),
    ('IQ', 'Iraq'), 
    ('IE', 'Ireland'), 
    ('IM', 'Isle of Man'),
    ('IL', 'Israel'), 
    ('IT', 'Italy'), 
    ('JM', 'Jamaica'), 
    ('JP', 'Japan'), 
    ('JE', 'Jersey'),
    ('JO', 'Jordan'), 
    ('KZ', 'Kazakhstan'), 
    ('KE', 'Kenya'), 
    ('KI', 'Kiribati'), 
    ('KP', 'Korea (DPRK)'),
    ('KR', 'Korea (the Republic of)'),
    ('KW', 'Kuwait'), 
    ('KG', 'Kyrgyzstan'), 
    ('LA', 'Lao People\'s Democratic Republic (the)'),
    ('LV', 'Latvia'), 
    ('LB', 'Lebanon'), 
    ('LS', 'Lesotho'), 
    ('LR', 'Liberia'), 
    ('LY', 'Libya'),
    ('LI', 'Liechtenstein'), 
    ('LT', 'Lithuania'), 
    ('LU', 'Luxembourg'), 
    ('MO', 'Macao'), 
    ('MK', 'Macedonia'),
    ('MG', 'Madagascar'), 
    ('MW', 'Malawi'), 
    ('MY', 'Malaysia'), 
    ('MV', 'Maldives'), 
    ('ML', 'Mali'), 
    ('MT', 'Malta'), 
    ('MH', 'Marshall Islands (the)'),
    ('MQ', 'Martinique'), 
    ('MR', 'Mauritania'), 
    ('MU', 'Mauritius'), 
    ('YT', 'Mayotte'),
    ('MX', 'Mexico'), 
    ('FM', 'Micronesia (Federated States of)'),
    ('MD', 'Moldova (the Republic of)'), 
    ('MC', 'Monaco'), 
    ('MN', 'Mongolia'), 
    ('ME', 'Montenegro'), 
    ('MS', 'Montserrat'), 
    ('MA', 'Morocco'), 
    ('MZ', 'Mozambique'), 
    ('MM', 'Myanmar'), 
    ('NA', 'Namibia'), 
    ('NR', 'Nauru'), 
    ('NP', 'Nepal'), 
    ('NL', 'Netherlands (the)'), 
    ('NC', 'New Caledonia'), 
    ('NZ', 'New Zealand'), 
    ('NI', 'Nicaragua'), 
    ('NE', 'Niger'), 
    ('NG', 'Nigeria'), 
    ('NU', 'Niue'), 
    ('NF', 'Norfolk Island'),
    ('MP', 'Northern Mariana Islands (the)'),
    ('NO', 'Norway'), 
    ('OM', 'Oman'), 
    ('PK', 'Pakistan'), 
    ('PW', 'Palau'), 
    ('PS', 'Palestine, State of'), 
    ('PA', 'Panama'), 
    ('PG', 'Papua New Guinea'), 
    ('PY', 'Paraguay'), 
    ('PE', 'Peru'), 
    ('PH', 'Philippines'), 
    ('PN', 'Pitcairn'), 
    ('PL', 'Poland'), 
    ('PT', 'Portugal'), 
    ('PR', 'Puerto Rico'), 
    ('QA', 'Qatar'), 
    ('RE', 'Reunion'), 
    ('RO', 'Romania'), 
    ('RU', 'Russian Federation (the)'), 
    ('RW', 'Rwanda'), 
    ('BL', 'Saint Barthelemy'),
    ('SH', 'Saint Helena, Ascension and TdC'), 
    ('KN', 'Saint Kitts and Nevis'), 
    ('LC', 'Saint Lucia'), 
    ('MF', 'Saint Martin (French part)'),
    ('PM', 'Saint Pierre and Miquelon'), 
    ('VC', 'Saint Vincent and the Grenadines'), 
    ('WS', 'Samoa'), 
    ('SM', 'San Marino'), 
    ('ST', 'Sao Tome and Principe'), 
    ('SA', 'Saudi Arabia'), 
    ('SN', 'Senegal'), 
    ('RS', 'Serbia'), 
    ('SC', 'Seychelles'), 
    ('SL', 'Sierra Leone'), 
    ('SG', 'Singapore'), 
    ('SX', 'Sint Maarten (Dutch part)'),
    ('SK', 'Slovakia'), 
    ('SI', 'Slovenia'), 
    ('SB', 'Solomon Islands'), 
    ('SO', 'Somalia'), 
    ('ZA', 'South Africa'), 
    ('SS', 'South Sudan'),
    ('ES', 'Spain'), 
    ('LK', 'Sri Lanka'), 
    ('SD', 'Sudan'), 
    ('SR', 'Suriname'), 
    ('SJ', 'Svalband and Jan Mayen'),
    ('SE', 'Sweden'), 
    ('CH', 'Switzerland'), 
    ('SY', 'Syrian Arab Republic'),
    ('TW', 'Taiwan'),
    ('TJ', 'Tajikistan'), 
    ('TZ', 'Tanzania, United Republic of'),
    ('TH', 'Thailand'), 
    ('TL', 'Timor-Leste'), 
    ('TG', 'Togo'), 
    ('TK', 'Tokelau'),
    ('TO', 'Tonga'), 
    ('TT', 'Trinidad and Tobago'), 
    ('TN', 'Tunisia'), 
    ('TR', 'Turkey'), 
    ('TM', 'Turkmenistan'), 
    ('TC', 'Turks and Caicos Islands (the)'), 
    ('TV', 'Tuvalu'), 
    ('UG', 'Uganda'), 
    ('UA', 'Ukraine'), 
    ('AE', 'United Arab Emirates'), 
    ('GB', 'United Kingdom'), 
    ('UY', 'Uruguay'), 
    ('UZ', 'Uzbekistan'), 
    ('VU', 'Vanuatu'), 
    ('VE', 'Venezuela (Bolivarian Republic of)'), 
    ('VN', 'Viet Nam'), 
    ('VG', 'Virgin Islands (British)'), 
    ('VI', 'Virgin Islands (U.S.)'),
    ('WF', 'Wallis and Futuna'), 
    ('EH', 'Western Sahara'), 
    ('YE', 'Yemen'), 
    ('ZM', 'Zambia'), 
    ('ZW', 'Zimbabwe'), 
)
