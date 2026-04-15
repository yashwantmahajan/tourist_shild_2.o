"""
Smart Tourist Shield AI - Main Flask Application
Complete Enterprise System with Flask-Login Authentication
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, TouristProfile, Alert, EvidenceLog, SOSRequest, EFIR, HospitalRequest, Criminal, CriminalDetection, GeoFence, Notification
from ai_engine import AIEngine
from pdf_generator import PDFGenerator
from datetime import datetime, timedelta
import random
import os
import re
import math

# Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-shield-ai-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tourist_shield.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['GOOGLE_MAPS_KEY'] = os.environ.get('GOOGLE_MAPS_KEY', 'AIzaSyDTQj3zpCqX9LIsxSyYYG2SrEyNShNoNHk')

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize AI Engine & PDF Generator
ai_engine = AIEngine()
pdf_gen = PDFGenerator()

# Ensure PDF directory exists
os.makedirs('static/pdf_reports', exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_config():
    return {'GOOGLE_MAPS_KEY': app.config.get('GOOGLE_MAPS_KEY', '')}

# ============== ERROR HANDLERS ==============

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('404.html'), 500

# ============== PUBLIC ROUTES ==============

@app.route('/')
def landing():
    """Public Landing Page"""
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login Page with Role-based Routing - supports username OR email"""
    if current_user.is_authenticated:
        if current_user.role == 'TOURIST':
            return redirect(url_for('tourist_dashboard'))
        elif current_user.role == 'POLICE':
            return redirect(url_for('police_dashboard'))
        else:
            return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        identifier = request.form.get('username')  # can be username or email
        password = request.form.get('password')
        
        # Try username first, then email
        user = User.query.filter_by(username=identifier).first()
        if not user:
            user = User.query.filter_by(email=identifier).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            
            if user.role == 'TOURIST':
                return redirect(url_for('tourist_dashboard'))
            elif user.role == 'POLICE':
                return redirect(url_for('police_dashboard'))
            else:
                return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username/email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('landing'))


# ============== TOURIST SIGNUP ==============

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Tourist Self-Registration with role-based fields"""
    if current_user.is_authenticated:
        return redirect(url_for('tourist_dashboard'))
    
    if request.method == 'POST':
        tourist_type = request.form.get('tourist_type', 'INDIAN').upper()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        mobile = request.form.get('mobile', '').strip()
        address = request.form.get('address', '').strip()
        from_location = request.form.get('from_location', '').strip()
        to_location = request.form.get('to_location', '').strip()
        tour_start = request.form.get('tour_start_date', '')
        tour_end = request.form.get('tour_end_date', '')
        
        # Validation
        errors = []
        
        if not first_name or not last_name:
            errors.append('First and Last name are required.')
        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors.append('Valid email is required.')
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if not from_location or not to_location:
            errors.append('Tour start and destination are required.')
        
        # Check uniqueness
        if User.query.filter_by(username=username).first():
            errors.append('Username already taken. Please choose another.')
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered. Please login or use another email.')
        
        # Type-specific validation
        aadhar = ''
        passport = ''
        if tourist_type == 'INDIAN':
            aadhar = re.sub(r'\s', '', request.form.get('aadhar_number', ''))
            if not re.match(r'^\d{12}$', aadhar):
                errors.append('Aadhar number must be exactly 12 digits.')
        else:
            passport = request.form.get('passport_number', '').strip().upper()
            if not re.match(r'^[A-Z0-9]{6,12}$', passport):
                errors.append('Passport number must be 6-12 alphanumeric characters.')
        
        # Phone validation
        clean_mobile = re.sub(r'[\s\-\+\(\)]', '', mobile)
        if not re.match(r'^\d{7,15}$', clean_mobile):
            errors.append('Valid mobile number is required (7-15 digits).')
        
        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('signup.html', form_data=request.form)
        
        try:
            # Create User
            user = User(username=username, email=email, role='TOURIST')
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            
            # Generate Digital ID
            if tourist_type == 'INDIAN':
                count = TouristProfile.query.filter_by(tourist_type='INDIAN').count()
                digital_id = f'TID-IND-{str(count + 1).zfill(4)}'
            else:
                count = TouristProfile.query.filter_by(tourist_type='FOREIGN').count()
                digital_id = f'TID-FOR-{str(count + 1).zfill(4)}'
            
            full_name = f"{first_name} {last_name}"
            
            # Parse dates
            from datetime import date as date_type
            t_start = datetime.strptime(tour_start, '%Y-%m-%d').date() if tour_start else None
            t_end = datetime.strptime(tour_end, '%Y-%m-%d').date() if tour_end else None
            
            # Create Tourist Profile
            profile = TouristProfile(
                user_id=user.id,
                first_name=first_name,
                last_name=last_name,
                name=full_name,
                digital_id=digital_id,
                tourist_type=tourist_type,
                email=email,
                contact=mobile,
                from_location=from_location,
                to_location=to_location,
                tour_start_date=t_start,
                tour_end_date=t_end,
                safety_score=95,
                status='Safe',
                zone_status='safe',
                current_lat=28.6139,
                current_lng=77.2090,
                last_location=from_location or 'Journey Start'
            )
            
            # Set type-specific fields
            if tourist_type == 'INDIAN':
                profile.aadhar_number = aadhar
                profile.address = address
                profile.nationality = 'Indian'
            else:
                profile.passport_number = passport
                profile.address = address
                profile.nationality = request.form.get('country', 'International')
                profile.country = request.form.get('country', '')
            
            db.session.add(profile)
            db.session.flush()
            
            # Welcome notification
            welcome_notif = Notification(
                user_id=user.id,
                tourist_id=profile.id,
                title='Welcome to Smart Tourist Shield!',
                message=f'Welcome {full_name}! Your tour from {from_location} to {to_location} is now registered. Stay safe!',
                notif_type='success',
                is_read=False
            )
            db.session.add(welcome_notif)
            
            db.session.commit()
            
            # Auto-login
            login_user(user)
            flash(f'Registration successful! Welcome, {full_name}! Your Tourist ID: {digital_id}', 'success')
            return redirect(url_for('tourist_dashboard'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'danger')
            return render_template('signup.html', form_data=request.form)
    
    return render_template('signup.html', form_data={})

# ============== TOURIST DASHBOARD ==============

@app.route('/tourist/dashboard')
@login_required
def tourist_dashboard():
    """Tourist Dashboard - Main View"""
    if current_user.role != 'TOURIST':
        if current_user.role == 'POLICE':
            flash('Access denied. Please use the Police dashboard.', 'danger')
            return redirect(url_for('police_dashboard'))
        else:
            flash('Access denied. Please use the Admin dashboard.', 'danger')
            return redirect(url_for('admin_dashboard'))
    
    # Get tourist profile
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    
    if not tourist_profile:
        flash('Tourist profile not found.', 'danger')
        return redirect(url_for('logout'))
    
    # Calculate current safety score
    recent_alerts = Alert.query.filter_by(tourist_id=tourist_profile.id).order_by(Alert.created_at.desc()).limit(10).all()
    safety_score = ai_engine.calculate_safety_score(tourist_profile, len(recent_alerts))
    risk_badge, badge_color = ai_engine.get_risk_badge(safety_score)
    
    # Update profile
    tourist_profile.safety_score = safety_score
    tourist_profile.status = risk_badge
    tourist_profile.last_update = datetime.utcnow()
    
    # Update zone status based on geo-fences
    active_fences = GeoFence.query.filter_by(is_active=True).all()
    in_any_zone = False
    for fence in active_fences:
        dist = _haversine(tourist_profile.current_lat, tourist_profile.current_lng,
                          fence.center_lat, fence.center_lng)
        if dist <= fence.radius_km:
            in_any_zone = True
            break
    tourist_profile.zone_status = 'safe' if in_any_zone or not active_fences else 'out_of_zone'
    
    db.session.commit()
    
    # Get behavioral flags
    behavior_flags = ai_engine.detect_behavioral_flags(tourist_profile)
    
    # Unread notifications count
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    
    # Get geo-fences for map display
    geo_fences = GeoFence.query.filter_by(is_active=True).all()
    geo_fences_data = [{
        'id': gf.id, 'name': gf.name, 'zone_type': gf.zone_type,
        'lat': gf.center_lat, 'lng': gf.center_lng,
        'radius': gf.radius_km * 1000,  # convert to meters for Leaflet
        'color': gf.color
    } for gf in geo_fences]
    
    import json
    return render_template('tourist_dashboard.html',
                           profile=tourist_profile,
                           safety_score=safety_score,
                           risk_badge=risk_badge,
                           badge_color=badge_color,
                           alerts=recent_alerts,
                           behavior_flags=behavior_flags,
                           unread_count=unread_count,
                           geo_fences_json=json.dumps(geo_fences_data))

# ============== ADMIN DASHBOARD ==============

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin Dashboard - Overview"""
    if current_user.role != 'ADMIN':
        flash('Access denied. Tourist accounts cannot access admin dashboard.', 'danger')
        return redirect(url_for('tourist_dashboard'))
    
    # Gather statistics
    total_tourists = TouristProfile.query.count()
    active_tourists = TouristProfile.query.filter(
        TouristProfile.last_update >= datetime.utcnow() - timedelta(hours=1)
    ).count()
    
    total_alerts = Alert.query.count()
    critical_alerts = Alert.query.filter_by(severity='critical').filter_by(status='active').count()
    
    sos_requests = SOSRequest.query.filter_by(status='pending').count()
    hospital_requests_count = HospitalRequest.query.filter_by(status='pending').count()
    total_efirs = EFIR.query.count()
    active_routes = TouristProfile.query.filter(
        TouristProfile.from_location != None,
        TouristProfile.to_location != None
    ).count()
    
    # Get all tourists for map
    all_tourists = TouristProfile.query.all()
    
    # Recent alerts
    recent_alerts = Alert.query.order_by(Alert.created_at.desc()).limit(15).all()
    
    # Active SOS
    active_sos = SOSRequest.query.filter_by(status='pending').order_by(SOSRequest.created_at.desc()).all()
    
    # Active Hospital Requests
    active_hospital = HospitalRequest.query.filter_by(status='pending').order_by(HospitalRequest.created_at.desc()).all()
    
    # Geo-fences
    geo_fences = GeoFence.query.all()
    import json
    geo_fences_data = [{
        'id': gf.id, 'name': gf.name, 'zone_type': gf.zone_type,
        'lat': gf.center_lat, 'lng': gf.center_lng,
        'radius': gf.radius_km * 1000,
        'color': gf.color, 'description': gf.description or '',
        'is_active': gf.is_active
    } for gf in geo_fences]
    
    stats = {
        'total_tourists': total_tourists,
        'active_tourists': active_tourists,
        'total_alerts': total_alerts,
        'critical_alerts': critical_alerts,
        'sos_requests': sos_requests,
        'hospital_requests': hospital_requests_count,
        'total_efirs': total_efirs,
        'active_routes': active_routes
    }
    
    return render_template('admin_dashboard.html',
                           stats=stats,
                           tourists=all_tourists,
                           alerts=recent_alerts,
                           sos_list=active_sos,
                           hospital_list=active_hospital,
                           geo_fences_json=json.dumps(geo_fences_data),
                           geo_fences=geo_fences)

# ============== POLICE DASHBOARD ==============

@app.route('/police/dashboard')
@login_required
def police_dashboard():
    """Police Dashboard - Overview"""
    if current_user.role != 'POLICE':
        flash('Access denied. Only police accounts can access this dashboard.', 'danger')
        if current_user.role == 'TOURIST':
            return redirect(url_for('tourist_dashboard'))
        else:
            return redirect(url_for('admin_dashboard'))
    
    # Gather statistics
    total_tourists = TouristProfile.query.count()
    active_sos = SOSRequest.query.filter_by(status='pending').count()
    total_alerts = Alert.query.filter_by(severity='critical').count()
    criminal_count = Criminal.query.filter_by(is_active=True).count()
    
    # Get all tourists for map
    all_tourists = TouristProfile.query.all()
    
    # Active SOS Requests
    sos_list = SOSRequest.query.filter(SOSRequest.status.in_(['pending', 'dispatched'])).order_by(SOSRequest.created_at.desc()).all()
    
    # Recent critical alerts
    recent_alerts = Alert.query.filter_by(severity='critical').order_by(Alert.created_at.desc()).limit(10).all()
    
    # Criminal detections
    criminal_detections = CriminalDetection.query.order_by(CriminalDetection.detected_at.desc()).limit(5).all()
    
    stats = {
        'total_tourists': total_tourists,
        'active_sos': active_sos,
        'critical_alerts': total_alerts,
        'criminal_count': criminal_count
    }
    
    return render_template('police_dashboard.html',
                           stats=stats,
                           tourists=all_tourists,
                           sos_list=sos_list,
                           alerts=recent_alerts,
                           criminal_detections=criminal_detections)

# ============== API ENDPOINTS ==============


def _haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two GPS points in kilometers"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


# ============== GEO-FENCE APIs ==============

@app.route('/api/geo-fence/list')
@login_required
def api_geo_fence_list():
    """Get all geo-fences"""
    if current_user.role not in ['ADMIN', 'POLICE']:
        return jsonify({'error': 'Unauthorized'}), 403
    fences = GeoFence.query.all()
    return jsonify([{
        'id': f.id, 'name': f.name, 'zone_type': f.zone_type,
        'lat': f.center_lat, 'lng': f.center_lng,
        'radius_km': f.radius_km, 'color': f.color,
        'description': f.description or '', 'is_active': f.is_active,
        'created_at': f.created_at.strftime('%Y-%m-%d %H:%M')
    } for f in fences])


@app.route('/api/geo-fence/add', methods=['POST'])
@login_required
def api_geo_fence_add():
    """Admin creates a geo-fence zone"""
    if current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    try:
        fence = GeoFence(
            name=data['name'],
            zone_type=data.get('zone_type', 'safe'),
            center_lat=float(data['lat']),
            center_lng=float(data['lng']),
            radius_km=float(data.get('radius_km', 1.0)),
            color='#10b981' if data.get('zone_type', 'safe') == 'safe' else '#ef4444',
            description=data.get('description', ''),
            created_by=current_user.username
        )
        db.session.add(fence)
        db.session.commit()
        return jsonify({'status': 'success', 'id': fence.id, 'message': f'Geo-fence "{fence.name}" created!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@app.route('/api/geo-fence/delete/<int:fence_id>', methods=['DELETE'])
@login_required
def api_geo_fence_delete(fence_id):
    """Admin deletes a geo-fence zone"""
    if current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    fence = GeoFence.query.get_or_404(fence_id)
    db.session.delete(fence)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Geo-fence deleted'})


@app.route('/api/geo-fence/toggle/<int:fence_id>', methods=['POST'])
@login_required
def api_geo_fence_toggle(fence_id):
    """Toggle geo-fence active status"""
    if current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    fence = GeoFence.query.get_or_404(fence_id)
    fence.is_active = not fence.is_active
    db.session.commit()
    return jsonify({'status': 'success', 'is_active': fence.is_active})


# ============== TOURIST ZONE STATUS ==============

@app.route('/api/tourist/zone-check')
@login_required
def api_tourist_zone_check():
    """Check if tourist is inside any active geo-fence.
    Accepts optional ?lat=&lng= from browser for real-time checking."""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist = TouristProfile.query.filter_by(user_id=current_user.id).first()
    if not tourist:
        return jsonify({'error': 'Profile not found'}), 404
    
    # Use live GPS from browser if provided, else stored DB coords
    try:
        check_lat = float(request.args.get('lat') or tourist.current_lat)
        check_lng = float(request.args.get('lng') or tourist.current_lng)
    except (TypeError, ValueError):
        check_lat = tourist.current_lat
        check_lng = tourist.current_lng
    
    # Persist live coords to DB if browser sent them
    if request.args.get('lat') and request.args.get('lng'):
        tourist.current_lat = check_lat
        tourist.current_lng = check_lng
        tourist.last_update = datetime.utcnow()
    fences = GeoFence.query.filter_by(is_active=True).all()
    current_zone = None
    in_zone = False
    
    for fence in fences:
        dist = _haversine(check_lat, check_lng, fence.center_lat, fence.center_lng)
        if dist <= fence.radius_km:
            in_zone = True
            current_zone = fence.name
            break
    
    zone_status = 'safe' if in_zone or not fences else 'out_of_zone'
    if tourist.zone_status != zone_status:
        tourist.zone_status = zone_status
        # Create notification if out of zone
        if zone_status == 'out_of_zone':
            notif = Notification(
                user_id=current_user.id,
                tourist_id=tourist.id,
                title='⚠️ Zone Alert',
                message='You have moved outside the designated safe zone. Please return to the approved area.',
                notif_type='warning',
                is_read=False
            )
            db.session.add(notif)
        db.session.commit()
    
    fences_data = [{'lat': f.center_lat, 'lng': f.center_lng,
                     'radius_km': f.radius_km, 'color': f.color,
                     'name': f.name, 'zone_type': f.zone_type}
                    for f in fences]

    return jsonify({
        'zone_status': zone_status,
        'in_zone': in_zone,
        'current_zone': current_zone,
        'lat': check_lat,
        'lng': check_lng,
        'fences': fences_data
    })


# ============== ADMIN TOURIST ROUTES ==============

@app.route('/api/admin/tourist-routes')
@login_required
def api_admin_tourist_routes():
    """Get all tourists with route data"""
    if current_user.role not in ['ADMIN', 'POLICE']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourists = TouristProfile.query.all()
    data = [{
        'id': t.id,
        'name': t.name,
        'digital_id': t.digital_id,
        'tourist_type': t.tourist_type,
        'from_location': t.from_location or 'N/A',
        'to_location': t.to_location or 'N/A',
        'tour_start_date': t.tour_start_date.strftime('%Y-%m-%d') if t.tour_start_date else 'N/A',
        'tour_end_date': t.tour_end_date.strftime('%Y-%m-%d') if t.tour_end_date else 'N/A',
        'zone_status': t.zone_status or 'safe',
        'safety_score': t.safety_score,
        'status': t.status,
        'lat': t.current_lat,
        'lng': t.current_lng
    } for t in tourists]
    return jsonify(data)


# ============== NOTIFICATIONS ==============

@app.route('/api/notifications')
@login_required
def api_get_notifications():
    """Get notifications for current user"""
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(20).all()
    return jsonify([{
        'id': n.id,
        'title': n.title or 'Notification',
        'message': n.message,
        'type': n.notif_type,
        'is_read': n.is_read,
        'time': n.created_at.strftime('%H:%M, %d %b')
    } for n in notifs])


@app.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def api_notifications_mark_read():
    """Mark all notifications as read"""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/api/notifications/unread-count')
@login_required
def api_notifications_unread_count():
    """Get unread notification count"""
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'count': count})


# ============== ROUTE RECOMMENDATIONS ==============

@app.route('/api/route-recommendations')
@login_required
def api_route_recommendations():
    """Basic route recommendations (popular destinations)"""
    popular_routes = [
        {'from': 'Delhi', 'to': 'Agra', 'highlight': 'Taj Mahal', 'distance': '200 km', 'duration': '3 hrs', 'safety': 'High'},
        {'from': 'Delhi', 'to': 'Jaipur', 'highlight': 'Pink City', 'distance': '280 km', 'duration': '4.5 hrs', 'safety': 'High'},
        {'from': 'Mumbai', 'to': 'Goa', 'highlight': 'Beaches & Culture', 'distance': '590 km', 'duration': '9 hrs', 'safety': 'High'},
        {'from': 'Varanasi', 'to': 'Bodhgaya', 'highlight': 'Spiritual Circuit', 'distance': '250 km', 'duration': '5 hrs', 'safety': 'Moderate'},
        {'from': 'Chennai', 'to': 'Mahabalipuram', 'highlight': 'Shore Temple', 'distance': '60 km', 'duration': '1.5 hrs', 'safety': 'High'},
        {'from': 'Kolkata', 'to': 'Darjeeling', 'highlight': 'Hill Station', 'distance': '600 km', 'duration': '12 hrs', 'safety': 'High'},
    ]
    return jsonify({'routes': popular_routes, 'mode': 'basic'})

@app.route('/api/tourist/status')
@login_required
def api_tourist_status():
    """Get current tourist status (AJAX polling)"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    
    if not tourist_profile:
        return jsonify({'error': 'Profile not found'}), 404
    
    # Check zone entry
    in_risk_zone, zone_name = ai_engine.detect_zone_entry(
        tourist_profile.current_lat,
        tourist_profile.current_lng
    )
    
    if in_risk_zone and random.random() < 0.3:  # 30% chance to create alert
        new_alert = Alert(
            tourist_id=tourist_profile.id,
            severity='high',
            alert_type='warning',
            message=f'⚠️ Entered high-risk zone: {zone_name}'
        )
        db.session.add(new_alert)
    
    # Random alert generation
    random_alert_data = ai_engine.generate_random_alert()
    if random_alert_data:
        new_alert = Alert(
            tourist_id=tourist_profile.id,
            severity=random_alert_data['severity'],
            alert_type=random_alert_data['type'],
            message=random_alert_data['message']
        )
        db.session.add(new_alert)
    
    # Recalculate safety score
    recent_alerts_count = Alert.query.filter_by(tourist_id=tourist_profile.id).count()
    new_score = ai_engine.calculate_safety_score(tourist_profile, recent_alerts_count)
    risk_badge, badge_color = ai_engine.get_risk_badge(new_score)
    
    tourist_profile.safety_score = new_score
    tourist_profile.status = risk_badge
    tourist_profile.last_update = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'safety_score': new_score,
        'status': risk_badge,
        'badge_color': badge_color,
        'location': tourist_profile.last_location,
        'lat': tourist_profile.current_lat,
        'lng': tourist_profile.current_lng
    })

@app.route('/api/tourist/update-location', methods=['POST'])
@login_required
def api_update_tourist_location():
    """Receive real GPS coordinates from tourist's browser"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    lat = data.get('lat')
    lng = data.get('lng')
    location_name = data.get('location_name', 'Unknown')
    if lat is None or lng is None:
        return jsonify({'error': 'Missing coordinates'}), 400
    profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        return jsonify({'error': 'Not found'}), 404
    profile.current_lat = float(lat)
    profile.current_lng = float(lng)
    profile.last_location = location_name
    profile.last_update = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'ok'})


@app.route('/api/tourist/ip-location')
@login_required
def api_ip_location():
    """Return approximate location from the visitor's IP — NO browser permission needed.
    Uses ip-api.com (free, no API key). Falls back to New Delhi if lookup fails."""
    import urllib.request
    import json as _json

    # Get the real client IP (handles reverse proxies)
    ip = (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
          or request.headers.get('X-Real-IP', '')
          or request.remote_addr
          or '')

    # Loopback / private IPs on localhost dev → use New Delhi for demo
    private_prefixes = ('127.', '10.', '192.168.', '172.', '::1', '')
    if any(ip.startswith(p) for p in private_prefixes):
        return jsonify({
            'lat': 28.6129, 'lng': 77.2295,
            'city': 'New Delhi', 'region': 'Delhi',
            'country': 'India', 'source': 'default_local'
        })

    try:
        url = f'http://ip-api.com/json/{ip}?fields=status,lat,lon,city,regionName,country'
        with urllib.request.urlopen(url, timeout=4) as resp:
            geo = _json.loads(resp.read().decode())
        if geo.get('status') == 'success':
            return jsonify({
                'lat': geo['lat'], 'lng': geo['lon'],
                'city': geo.get('city', ''), 'region': geo.get('regionName', ''),
                'country': geo.get('country', ''), 'source': 'ip'
            })
    except Exception:
        pass

    # Final fallback — India Gate, New Delhi
    return jsonify({
        'lat': 28.6139, 'lng': 77.2090,
        'city': 'New Delhi', 'region': 'Delhi',
        'country': 'India', 'source': 'fallback'
    })


@app.route('/api/admin/all-tourists-location')
@login_required
def api_all_tourist_locations():
    """Return live GPS positions of all tourists for admin map"""
    if current_user.role != 'ADMIN':
        return jsonify([]), 403
    profiles = TouristProfile.query.all()
    return jsonify([{
        'id': p.id, 'name': p.name,
        'lat': p.current_lat, 'lng': p.current_lng,
        'status': p.status, 'safety_score': p.safety_score,
        'last_location': p.last_location
    } for p in profiles if p.current_lat])

@app.route('/api/tourist/update-route', methods=['POST'])
@login_required
def api_tourist_update_route():
    """Update tourist from/to locations dynamically"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    data = request.get_json()
    from_loc = data.get('from_location', '').strip()
    to_loc = data.get('to_location', '').strip()
    
    if from_loc:
        tourist_profile.from_location = from_loc
    if to_loc:
        tourist_profile.to_location = to_loc
        
    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': 'Route updated successfully',
        'from_location': tourist_profile.from_location,
        'to_location': tourist_profile.to_location
    })

@app.route('/api/tourist/alerts')
@login_required
def api_tourist_alerts():
    """Get latest alerts for tourist"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    alerts = Alert.query.filter_by(tourist_id=tourist_profile.id).order_by(Alert.created_at.desc()).limit(10).all()
    
    alerts_data = [{
        'id': alert.id,
        'severity': alert.severity,
        'type': alert.alert_type,
        'message': alert.message,
        'time': alert.created_at.strftime('%H:%M:%S'),
        'status': alert.status
    } for alert in alerts]
    
    return jsonify(alerts_data)

@app.route('/api/tourist/panic', methods=['POST'])
@login_required
def panic_sos():
    """Handle panic SOS button"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    
    # Create SOS Request
    sos_request = SOSRequest(
        tourist_id=tourist_profile.id,
        location=tourist_profile.last_location,
        latitude=tourist_profile.current_lat,
        longitude=tourist_profile.current_lng
    )
    db.session.add(sos_request)
    
    # Create Hospital Request
    hospital_request = HospitalRequest(
        tourist_id=tourist_profile.id,
        location=tourist_profile.last_location,
        latitude=tourist_profile.current_lat,
        longitude=tourist_profile.current_lng
    )
    db.session.add(hospital_request)
    
    # Create Critical Alert
    alert = Alert(
        tourist_id=tourist_profile.id,
        severity='critical',
        alert_type='sos',
        message=f'🚨 PANIC SOS: {tourist_profile.name} in IMMEDIATE DANGER!'
    )
    db.session.add(alert)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'sos_id': sos_request.id,
        'hospital_id': hospital_request.id
    })

@app.route('/api/tourist/panic/police', methods=['POST'])
@login_required
def panic_police_only():
    """Separate Police SOS - Only dispatches police units"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    
    # Create Police SOS Request
    sos_request = SOSRequest(
        tourist_id=tourist_profile.id,
        location=tourist_profile.last_location,
        latitude=tourist_profile.current_lat,
        longitude=tourist_profile.current_lng,
        status='pending'
    )
    db.session.add(sos_request)
    
    # Create Critical Alert for Police
    alert = Alert(
        tourist_id=tourist_profile.id,
        severity='critical',
        alert_type='sos',
        message=f'🚨 POLICE SOS: {tourist_profile.name} needs immediate police assistance!'
    )
    db.session.add(alert)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Police SOS sent successfully',
        'sos_id': sos_request.id
    })

@app.route('/api/tourist/panic/hospital', methods=['POST'])
@login_required
def panic_hospital_only():
    """Separate Hospital SOS - Only dispatches ambulance"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    
    # Simulate nearest hospital location (offset from tourist location)
    import math
    hospital_offset_lat = random.uniform(0.01, 0.03)  # ~1-3 km away
    hospital_offset_lng = random.uniform(0.01, 0.03)
    ambulance_start_lat = tourist_profile.current_lat + hospital_offset_lat
    ambulance_start_lng = tourist_profile.current_lng + hospital_offset_lng
    
    # Calculate initial distance using Haversine formula
    def calculate_distance(lat1, lon1, lat2, lon2):
        """Calculate distance between two points in kilometers"""
        R = 6371  # Earth's radius in kilometers
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) * \
            math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    initial_distance = calculate_distance(
        ambulance_start_lat, ambulance_start_lng,
        tourist_profile.current_lat, tourist_profile.current_lng
    )
    
    # Estimate arrival time (assuming 40 km/h average speed in city)
    eta_minutes = int((initial_distance / 40) * 60)
    
    # Create Hospital Request with ambulance tracking
    hospital_request = HospitalRequest(
        tourist_id=tourist_profile.id,
        location=tourist_profile.last_location,
        latitude=tourist_profile.current_lat,
        longitude=tourist_profile.current_lng,
        status='dispatched',
        assigned_unit=f'AMB-{random.randint(100, 999)}',
        # Ambulance tracking fields
        ambulance_lat=ambulance_start_lat,
        ambulance_lng=ambulance_start_lng,
        ambulance_status='assigned',
        estimated_arrival_time=eta_minutes,
        distance_remaining=initial_distance,
        last_location_update=datetime.utcnow()
    )
    db.session.add(hospital_request)
    
    # Create Critical Alert for Medical
    alert = Alert(
        tourist_id=tourist_profile.id,
        severity='critical',
        alert_type='medical',
        message=f'🚑 MEDICAL EMERGENCY: {tourist_profile.name} needs immediate medical assistance!'
    )
    db.session.add(alert)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Ambulance dispatched successfully',
        'hospital_id': hospital_request.id,
        'ambulance_unit': hospital_request.assigned_unit,
        'eta_minutes': eta_minutes
    })


# ============== AMBULANCE TRACKING API ==============

@app.route('/api/ambulance/track/<int:hospital_req_id>')
@login_required
def api_ambulance_track(hospital_req_id):
    """Get current ambulance tracking data for a specific hospital request"""
    hospital_req = HospitalRequest.query.get_or_404(hospital_req_id)
    
    # Access control: tourist (own request only), police, admin
    if current_user.role == 'TOURIST':
        tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
        if hospital_req.tourist_id != tourist_profile.id:
            return jsonify({'error': 'Unauthorized'}), 403
    elif current_user.role not in ['POLICE', 'ADMIN']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if not hospital_req.ambulance_lat or not hospital_req.ambulance_lng:
        return jsonify({'error': 'Ambulance location not available'}), 404
    
    return jsonify({
        'hospital_req_id': hospital_req.id,
        'ambulance_unit': hospital_req.assigned_unit,
        'ambulance_location': {
            'lat': hospital_req.ambulance_lat,
            'lng': hospital_req.ambulance_lng
        },
        'tourist_location': {
            'lat': hospital_req.latitude,
            'lng': hospital_req.longitude
        },
        'status': hospital_req.ambulance_status,
        'eta_minutes': hospital_req.estimated_arrival_time,
        'distance_km': round(hospital_req.distance_remaining, 2) if hospital_req.distance_remaining else 0,
        'last_update': hospital_req.last_location_update.strftime('%Y-%m-%d %H:%M:%S') if hospital_req.last_location_update else None,
        'tourist_name': hospital_req.tourist.name,
        'tourist_digital_id': hospital_req.tourist.digital_id
    })

@app.route('/api/ambulance/simulate/<int:hospital_req_id>', methods=['POST'])
@login_required
def api_ambulance_simulate(hospital_req_id):
    """Simulate ambulance movement toward tourist (called automatically every 10 seconds)"""
    hospital_req = HospitalRequest.query.get_or_404(hospital_req_id)
    
    # Access control
    if current_user.role == 'TOURIST':
        tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
        if hospital_req.tourist_id != tourist_profile.id:
            return jsonify({'error': 'Unauthorized'}), 403
    elif current_user.role not in ['POLICE', 'ADMIN']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Check if already arrived
    if hospital_req.ambulance_status == 'arrived':
        return jsonify({'status': 'already_arrived', 'message': 'Ambulance has already arrived'})
    
    import math
    
    def calculate_distance(lat1, lon1, lat2, lon2):
        """Calculate distance between two points in kilometers"""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) * \
            math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    # Calculate current distance
    current_distance = calculate_distance(
        hospital_req.ambulance_lat, hospital_req.ambulance_lng,
        hospital_req.latitude, hospital_req.longitude
    )
    
    # If within 50 meters, mark as arrived
    if current_distance < 0.05:  # 50 meters
        hospital_req.ambulance_status = 'arrived'
        hospital_req.ambulance_lat = hospital_req.latitude
        hospital_req.ambulance_lng = hospital_req.longitude
        hospital_req.estimated_arrival_time = 0
        hospital_req.distance_remaining = 0
        hospital_req.status = 'resolved'
        hospital_req.last_location_update = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'status': 'arrived',
            'message': 'Ambulance has arrived at tourist location',
            'ambulance_status': 'arrived'
        })
    
    # Move ambulance toward tourist (simulate movement)
    # Move approximately 0.5-1 km per update (simulating 40 km/h with 10-second updates)
    movement_fraction = min(0.15, current_distance * 0.2)  # Move 15-20% closer each update
    
    lat_diff = hospital_req.latitude - hospital_req.ambulance_lat
    lng_diff = hospital_req.longitude - hospital_req.ambulance_lng
    
    hospital_req.ambulance_lat += lat_diff * movement_fraction
    hospital_req.ambulance_lng += lng_diff * movement_fraction
    
    # Recalculate distance
    new_distance = calculate_distance(
        hospital_req.ambulance_lat, hospital_req.ambulance_lng,
        hospital_req.latitude, hospital_req.longitude
    )
    
    # Update ETA (assuming 40 km/h average speed)
    new_eta = int((new_distance / 40) * 60)
    
    # Update status based on progress
    if hospital_req.ambulance_status == 'assigned':
        hospital_req.ambulance_status = 'on_the_way'
    
    hospital_req.distance_remaining = new_distance
    hospital_req.estimated_arrival_time = new_eta
    hospital_req.last_location_update = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'ambulance_status': hospital_req.ambulance_status,
        'distance_remaining': round(new_distance, 2),
        'eta_minutes': new_eta,
        'ambulance_location': {
            'lat': hospital_req.ambulance_lat,
            'lng': hospital_req.ambulance_lng
        }
    })

@app.route('/api/tourist/active-ambulance')
@login_required
def api_tourist_active_ambulance():
    """Get active ambulance tracking for current tourist"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    
    # Find most recent active hospital request
    active_request = HospitalRequest.query.filter_by(
        tourist_id=tourist_profile.id
    ).filter(
        HospitalRequest.ambulance_status.in_(['assigned', 'on_the_way'])
    ).order_by(HospitalRequest.created_at.desc()).first()
    
    if not active_request:
        return jsonify({'active': False, 'message': 'No active ambulance'})
    
    return jsonify({
        'active': True,
        'hospital_req_id': active_request.id,
        'ambulance_unit': active_request.assigned_unit,
        'ambulance_status': active_request.ambulance_status,
        'eta_minutes': active_request.estimated_arrival_time,
        'distance_km': round(active_request.distance_remaining, 2) if active_request.distance_remaining else 0
    })

@app.route('/api/admin/active-ambulances')
@login_required
def api_admin_active_ambulances():
    """Get all active ambulances for admin/police dashboard"""
    if current_user.role not in ['ADMIN', 'POLICE']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    active_ambulances = HospitalRequest.query.filter(
        HospitalRequest.ambulance_status.in_(['assigned', 'on_the_way'])
    ).order_by(HospitalRequest.created_at.desc()).all()
    
    ambulances_data = [{
        'id': req.id,
        'ambulance_unit': req.assigned_unit,
        'tourist_name': req.tourist.name,
        'tourist_digital_id': req.tourist.digital_id,
        'ambulance_location': {
            'lat': req.ambulance_lat,
            'lng': req.ambulance_lng
        },
        'tourist_location': {
            'lat': req.latitude,
            'lng': req.longitude
        },
        'status': req.ambulance_status,
        'eta_minutes': req.estimated_arrival_time,
        'distance_km': round(req.distance_remaining, 2) if req.distance_remaining else 0,
        'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for req in active_ambulances]
    
    return jsonify({'ambulances': ambulances_data, 'count': len(ambulances_data)})

@app.route('/api/admin/live-data')
@login_required
def api_admin_live_data():
    """Get live data for admin dashboard"""
    if current_user.role not in ['ADMIN', 'POLICE']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourists = TouristProfile.query.all()
    
    tourists_data = [{
        'id': t.id,
        'digital_id': t.digital_id,
        'name': t.name,
        'safety_score': t.safety_score,
        'status': t.status,
        'location': t.last_location,
        'lat': t.current_lat,
        'lng': t.current_lng
    } for t in tourists]
    
    return jsonify(tourists_data)

@app.route('/api/admin/dispatch/<int:sos_id>', methods=['POST'])
@login_required
def api_dispatch_sos(sos_id):
    """Dispatch police for SOS"""
    if current_user.role not in ['ADMIN', 'POLICE']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    sos = SOSRequest.query.get_or_404(sos_id)
    sos.status = 'dispatched'
    sos.assigned_officer = 'Officer Kumar'
    sos.notes = 'Units dispatched to location'
    
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Police units dispatched'})

@app.route('/api/admin/dispatch/hospital/<int:hospital_req_id>', methods=['POST'])
@login_required
def api_dispatch_hospital(hospital_req_id):
    """Dispatch ambulance for hospital request"""
    if current_user.role not in ['ADMIN', 'POLICE']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    hospital_req = HospitalRequest.query.get_or_404(hospital_req_id)
    
    # Update basic dispatch info
    hospital_req.status = 'dispatched'
    hospital_req.assigned_unit = f'AMB-{random.randint(100, 999)}'
    hospital_req.notes = 'Ambulance dispatched to location'
    
    # Initialize ambulance tracking
    # Set ambulance starting location (simulate hospital location near tourist)
    if hospital_req.latitude and hospital_req.longitude:
        # Place ambulance 0.02 degrees away (roughly 2km)
        hospital_req.ambulance_lat = hospital_req.latitude + 0.02
        hospital_req.ambulance_lng = hospital_req.longitude + 0.01
        
        # Calculate initial distance (roughly 2-3 km)
        from math import radians, sin, cos, sqrt, atan2
        
        lat1, lon1 = radians(hospital_req.ambulance_lat), radians(hospital_req.ambulance_lng)
        lat2, lon2 = radians(hospital_req.latitude), radians(hospital_req.longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance_km = 6371 * c
        
        hospital_req.distance_remaining = distance_km
        hospital_req.estimated_arrival_time = int((distance_km / 40) * 60)  # 40 km/h average speed
        hospital_req.ambulance_status = 'assigned'
        hospital_req.last_location_update = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'status': 'success', 
        'message': f'Ambulance {hospital_req.assigned_unit} dispatched successfully!',
        'ambulance_unit': hospital_req.assigned_unit
    })

@app.route('/api/admin/create-tourist-id', methods=['POST'])
@login_required
def api_create_tourist_id():
    """Create new tourist ID (Indian or Foreign)"""
    if current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    tourist_type = data.get('tourist_type')  # 'INDIAN' or 'FOREIGN'
    
    try:
        # Create User account
        username = f"tourist_{random.randint(1000, 9999)}"
        user = User(username=username, role='TOURIST')
        user.set_password('tourist@123')
        db.session.add(user)
        db.session.flush()
        
        # Generate Digital ID
        if tourist_type == 'INDIAN':
            count = TouristProfile.query.filter_by(tourist_type='INDIAN').count()
            digital_id = f'TID-IND-{str(count + 1).zfill(4)}'
        else:
            count = TouristProfile.query.filter_by(tourist_type='FOREIGN').count()
            digital_id = f'TID-FOR-{str(count + 1).zfill(4)}'
        
        # Create Tourist Profile
        profile = TouristProfile(
            user_id=user.id,
            name=data.get('name'),
            digital_id=digital_id,
            tourist_type=tourist_type,
            contact=data.get('contact') or data.get('mobile'),
            safety_score=95,
            status='Safe'
        )
        
        # Set type-specific fields
        if tourist_type == 'INDIAN':
            profile.aadhar_number = data.get('aadhar_number')
            profile.address = data.get('address')
            profile.nationality = 'Indian'
        else:
            profile.passport_number = data.get('passport_number')
            profile.email = data.get('email')
            profile.country = data.get('country')
            profile.nationality = data.get('country')
        
        db.session.add(profile)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Tourist ID {digital_id} created successfully',
            'digital_id': digital_id,
            'username': username
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/admin/hospital-requests', methods=['GET'])
@login_required
def api_get_hospital_requests():
    """Get all pending hospital requests"""
    if current_user.role not in ['ADMIN', 'POLICE']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    requests_list = HospitalRequest.query.filter_by(status='pending').order_by(HospitalRequest.created_at.desc()).all()
    
    data = [{
        'id': req.id,
        'tourist_name': req.tourist.name,
        'digital_id': req.tourist.digital_id,
        'location': req.location,
        'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'status': req.status
    } for req in requests_list]
    
    return jsonify(data)

# ============== PDF ENDPOINTS ==============

@app.route('/tourist/pdf/safety-report')
@login_required
def tourist_pdf_safety_report():
    """Generate and download tourist safety report PDF"""
    if current_user.role != 'TOURIST':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    alerts = Alert.query.filter_by(tourist_id=tourist_profile.id).order_by(Alert.created_at.desc()).limit(10).all()
    
    filename = f'safety_report_{tourist_profile.digital_id}_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    
    pdf_gen.generate_tourist_safety_report(tourist_profile, alerts, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/admin/pdf/daily-summary')
@login_required
def admin_pdf_daily_summary():
    """Generate admin daily summary PDF"""
    if current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourists = TouristProfile.query.all()
    sos_requests = SOSRequest.query.filter_by(status='pending').all()
    alerts = Alert.query.filter(Alert.severity.in_(['high', 'critical'])).order_by(Alert.created_at.desc()).limit(50).all()
    
    filename = f'daily_summary_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    
    pdf_gen.generate_daily_summary_pdf(tourists, sos_requests, alerts, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/admin/pdf/sos-report')
@login_required
def admin_pdf_sos_report():
    """Generate admin SOS report PDF"""
    if current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    
    sos_requests = SOSRequest.query.order_by(SOSRequest.created_at.desc()).all()
    hospital_requests = HospitalRequest.query.order_by(HospitalRequest.created_at.desc()).all()
    
    filename = f'admin_sos_report_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_sos_report_pdf(sos_requests, hospital_requests, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/admin/pdf/evidence-logs')
@login_required
def admin_pdf_evidence_logs():
    """Generate admin evidence logs PDF"""
    if current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    
    evidence = EvidenceLog.query.order_by(EvidenceLog.timestamp.desc()).all()
    
    filename = f'admin_evidence_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_evidence_logs_pdf(evidence, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/admin/pdf/efir-archive')
@login_required
def admin_pdf_efir_archive():
    """Generate admin E-FIR archive PDF"""
    if current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    
    sos_requests = SOSRequest.query.filter_by(status='dispatched').order_by(SOSRequest.created_at.desc()).all()
    
    filename = f'admin_efir_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_efir_archive_pdf(sos_requests, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

# ============== TOURIST PDF DOWNLOADS ==============

@app.route('/tourist/pdf/alert-history')
@login_required
def tourist_pdf_alert_history():
    """Generate Alert History PDF for current tourist"""
    if current_user.role != 'TOURIST':
        return "Unauthorized", 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    alerts = Alert.query.filter_by(tourist_id=tourist_profile.id).order_by(Alert.created_at.desc()).all()
    
    filename = f'alert_history_{tourist_profile.digital_id}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_alert_history_pdf(tourist_profile, alerts, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=f'Alert_History_{tourist_profile.digital_id}.pdf')

@app.route('/tourist/pdf/digital-id')
@login_required
def tourist_pdf_digital_id():
    """Generate Digital ID Card PDF for current tourist"""
    if current_user.role != 'TOURIST':
        return "Unauthorized", 403
    
    tourist_profile = TouristProfile.query.filter_by(user_id=current_user.id).first()
    
    filename = f'digital_id_{tourist_profile.digital_id}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_digital_id_card_pdf(tourist_profile, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=f'Digital_ID_{tourist_profile.digital_id}.pdf')

# ============== POLICE PDF DOWNLOADS ==============

@app.route('/police/pdf/daily-summary')
@login_required
def police_pdf_daily_summary():
    """Generate police daily summary PDF"""
    if current_user.role != 'POLICE':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourists = TouristProfile.query.all()
    sos_requests = SOSRequest.query.filter_by(status='pending').all()
    alerts = Alert.query.filter(Alert.severity.in_(['high', 'critical'])).order_by(Alert.created_at.desc()).limit(50).all()
    
    filename = f'police_daily_summary_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_daily_summary_pdf(tourists, sos_requests, alerts, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/police/pdf/sos-report')
@login_required
def police_pdf_sos_report():
    """Generate police SOS report PDF"""
    if current_user.role != 'POLICE':
        return jsonify({'error': 'Unauthorized'}), 403
    
    sos_requests = SOSRequest.query.order_by(SOSRequest.created_at.desc()).all()
    hospital_requests = HospitalRequest.query.order_by(HospitalRequest.created_at.desc()).all()
    
    filename = f'police_sos_report_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_sos_report_pdf(sos_requests, hospital_requests, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/police/pdf/evidence-logs')
@login_required
def police_pdf_evidence_logs():
    """Generate police evidence logs PDF"""
    if current_user.role != 'POLICE':
        return jsonify({'error': 'Unauthorized'}), 403
    
    evidence = EvidenceLog.query.order_by(EvidenceLog.timestamp.desc()).all()
    
    filename = f'police_evidence_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_evidence_logs_pdf(evidence, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/police/pdf/efir-archive')
@login_required
def police_pdf_efir_archive():
    """Generate police E-FIR archive PDF"""
    if current_user.role != 'POLICE':
        return jsonify({'error': 'Unauthorized'}), 403
    
    sos_requests = SOSRequest.query.filter_by(status='dispatched').order_by(SOSRequest.created_at.desc()).all()
    
    filename = f'police_efir_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    pdf_gen.generate_efir_archive_pdf(sos_requests, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/police/tourist/<int:tourist_id>/download-info')
@login_required
def police_download_tourist_info(tourist_id):
    """Download individual tourist information PDF for police"""
    if current_user.role != 'POLICE':
        return jsonify({'error': 'Unauthorized'}), 403
    
    tourist_profile = TouristProfile.query.get_or_404(tourist_id)
    alerts = Alert.query.filter_by(tourist_id=tourist_profile.id).order_by(Alert.created_at.desc()).limit(20).all()
    
    filename = f'tourist_info_{tourist_profile.digital_id}_{datetime.now().strftime("%Y%m%d")}.pdf'
    filepath = os.path.join('static', 'pdf_reports', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # Use existing tourist safety report method
    pdf_gen.generate_tourist_safety_report(tourist_profile, alerts, filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)


# ============== ERROR HANDLERS ==============


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# ============== RUN APPLICATION ==============

import os

port = int(os.environ.get("PORT", 10000))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)