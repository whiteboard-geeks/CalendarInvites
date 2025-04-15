"""
Configuration file for consultant-specific information.
This centralized structure allows for dynamic selection of consultants.
"""

CONSULTANTS = {
    "barbara_pigg": {
        "basic_info": {
            "full_name": "Barbara Pigg",
            "job_title": "CEO of Whiteboard Geeks",
            "email": "barbara.pigg@whiteboardgeeks.com",
            "crm_id_value": "Barbara Pigg",  # Value used in Close CRM filtering
            "first_name": "Barbara",
            "last_initial": "P",
        },
        "calendar": {"calendar_id": "barbara.pigg@whiteboardgeeks.com"},
        "meeting": {
            "zoom_url": "https://us02web.zoom.us/j/4960127137",
            "zoom_id": "496 012 7137",
            "one_tap_mobile": [
                "+16469313860,,4960127137# US",
                "+13017158592,,4960127137# US (Washington DC)",
            ],
            "dial_in_numbers": [
                "+1 646 931 3860 US",
                "+1 301 715 8592 US (Washington DC)",
                "+1 305 224 1968 US",
                "+1 309 205 3325 US",
                "+1 312 626 6799 US (Chicago)",
                "+1 646 558 8656 US (New York)",
                "+1 346 248 7799 US (Houston)",
                "+1 360 209 5623 US",
                "+1 386 347 5053 US",
                "+1 507 473 4847 US",
                "+1 564 217 2000 US",
                "+1 669 444 9171 US",
                "+1 669 900 9128 US (San Jose)",
                "+1 689 278 1000 US",
                "+1 719 359 4580 US",
                "+1 253 205 0468 US",
                "+1 253 215 8782 US (Tacoma)",
            ],
        },
        "templates": {
            "title": "Intro {{first_name}} {{last_initial}} @  {{company}} + Barbara P @ Whiteboard Geeks",
            "description": """Hi {{first_name}},

I'm the CEO of Whiteboard Geeks, we make whiteboard videos to simplify complex messages for all sorts of companies. Not terribly long ago I sent you a package with what we call a 'Video Card' or 'Video Brochure'. With the way the mail goes & hybrid work schedules, I wasn't sure if it arrived so I thought I'd invite you to a quick meeting.

I'm hoping to share more about our process for telling your most important story, and explain how we've been able to drive great results for companies like Eli Lilly, Eisai Pharmaceuticals, Tyson Foods, Michelin Tires, IBM and Cleveland Clinic. 

If this time doesn't work for you please feel free to propose one that does. Whatever is convenient.

Agenda:
- Share science behind the Whiteboard Geeks success stories, benchmarking data, and observed industry trends
- Learn about your current objectives and challenges
- Get feedback on the usefulness of Whiteboard Geeks services for your organization
- Plus we'll unlock the vault and show you videos related to your specific challenge-because videos are fun 😊🎥⭐

As a bonus: I'll give you a fun hand-drawn virtual background just for showing your smiling face! Yay! We get lots of compliments on our backgrounds…and now you can have one! 

Zoom Call information:
Barbara Pigg is inviting you to a scheduled Zoom meeting.

Topic: Barbara Pigg's Personal Meeting Room

Join Zoom Meeting
https://us02web.zoom.us/j/4960127137

Meeting ID: 496 012 7137

---

One tap mobile
+16469313860,,4960127137# US
+13017158592,,4960127137# US (Washington DC)

---

Dial by your location
• +1 646 931 3860 US
• +1 301 715 8592 US (Washington DC)
• +1 305 224 1968 US
• +1 309 205 3325 US
• +1 312 626 6799 US (Chicago)
• +1 646 558 8656 US (New York)
• +1 346 248 7799 US (Houston)
• +1 360 209 5623 US
• +1 386 347 5053 US
• +1 507 473 4847 US
• +1 564 217 2000 US
• +1 669 444 9171 US
• +1 669 900 9128 US (San Jose)
• +1 689 278 1000 US
• +1 719 359 4580 US
• +1 253 205 0468 US
• +1 253 215 8782 US (Tacoma)

Meeting ID: 496 012 7137

Find your local number: https://us02web.zoom.us/u/ksKzmwpEc""",
        },
        "crm_integration": {
            "custom_activity_type_id": "actitype_0CmcjmRFeEsO3yJFnLLVpS"
        },
    },
    "april_lowrie": {
        "basic_info": {
            "full_name": "April Lowrie",
            "job_title": "Creative Director",
            "email": "april.lowrie@whiteboardgeeks.com",
            "crm_id_value": "user_wOfS9vCRRQt7nQAaij3dCSr38xadW6N7fTMjMbHF88n",
            "first_name": "April",
            "last_initial": "L",
        },
        "calendar": {"calendar_id": "april.lowrie@whiteboardgeeks.com"},
        "meeting": {
            # TODO: Update with April's actual Zoom information
            "zoom_url": "PLACEHOLDER - UPDATE WITH APRIL'S ZOOM URL",
            "zoom_id": "PLACEHOLDER - UPDATE WITH APRIL'S ZOOM ID",
            # Using same one-tap mobile and dial-in numbers as Barbara for now
            "one_tap_mobile": [
                "+16469313860,,4960127137# US",
                "+13017158592,,4960127137# US (Washington DC)",
            ],
            "dial_in_numbers": [
                "+1 646 931 3860 US",
                "+1 301 715 8592 US (Washington DC)",
                "+1 305 224 1968 US",
                "+1 309 205 3325 US",
                "+1 312 626 6799 US (Chicago)",
                "+1 646 558 8656 US (New York)",
                "+1 346 248 7799 US (Houston)",
                "+1 360 209 5623 US",
                "+1 386 347 5053 US",
                "+1 507 473 4847 US",
                "+1 564 217 2000 US",
                "+1 669 444 9171 US",
                "+1 669 900 9128 US (San Jose)",
                "+1 689 278 1000 US",
                "+1 719 359 4580 US",
                "+1 253 205 0468 US",
                "+1 253 215 8782 US (Tacoma)",
            ],
        },
        "templates": {
            "title": "Intro {{first_name}} {{last_initial}} @  {{company}} + April L @ Whiteboard Geeks",
            # TODO: Update with April's customized description template
            "description": """Hi {{first_name}},

# TODO: Customize this template for April Lowrie

I'm the Creative Director of Whiteboard Geeks, we make whiteboard videos to simplify complex messages for all sorts of companies. Not terribly long ago we sent you a package with what we call a 'Video Card' or 'Video Brochure'. With the way the mail goes & hybrid work schedules, I wasn't sure if it arrived so I thought I'd invite you to a quick meeting.

I'm hoping to share more about our process for telling your most important story, and explain how we've been able to drive great results for companies like Eli Lilly, Eisai Pharmaceuticals, Tyson Foods, Michelin Tires, IBM and Cleveland Clinic. 

If this time doesn't work for you please feel free to propose one that does. Whatever is convenient.

Agenda:
- Share science behind the Whiteboard Geeks success stories, benchmarking data, and observed industry trends
- Learn about your current objectives and challenges
- Get feedback on the usefulness of Whiteboard Geeks services for your organization
- Plus we'll unlock the vault and show you videos related to your specific challenge-because videos are fun 😊🎥⭐

As a bonus: I'll give you a fun hand-drawn virtual background just for showing your smiling face! Yay! We get lots of compliments on our backgrounds…and now you can have one! 

Zoom Call information:
April Lowrie is inviting you to a scheduled Zoom meeting.

Topic: April Lowrie's Personal Meeting Room

Join Zoom Meeting
[PLACEHOLDER - UPDATE WITH APRIL'S ZOOM URL]

Meeting ID: [PLACEHOLDER - UPDATE WITH APRIL'S ZOOM ID]

---

One tap mobile
+16469313860,,4960127137# US
+13017158592,,4960127137# US (Washington DC)

---

Dial by your location
• +1 646 931 3860 US
• +1 301 715 8592 US (Washington DC)
• +1 305 224 1968 US
• +1 309 205 3325 US
• +1 312 626 6799 US (Chicago)
• +1 646 558 8656 US (New York)
• +1 346 248 7799 US (Houston)
• +1 360 209 5623 US
• +1 386 347 5053 US
• +1 507 473 4847 US
• +1 564 217 2000 US
• +1 669 444 9171 US
• +1 669 900 9128 US (San Jose)
• +1 689 278 1000 US
• +1 719 359 4580 US
• +1 253 205 0468 US
• +1 253 215 8782 US (Tacoma)

Meeting ID: [PLACEHOLDER - UPDATE WITH APRIL'S ZOOM ID]

Find your local number: https://us02web.zoom.us/u/ksKzmwpEc""",
        },
        "crm_integration": {
            "custom_activity_type_id": "actitype_0CmcjmRFeEsO3yJFnLLVpS"
        },
    },
}


# Helper function to get consultant data
def get_consultant(consultant_id):
    """
    Get consultant configuration by ID.
    Returns None if consultant_id is not found.
    """
    return CONSULTANTS.get(consultant_id)


# Get list of available consultants for UI
def get_consultant_choices():
    """
    Returns a list of tuples (id, display_name) for all available consultants.
    Suitable for use in dropdown menus.
    """
    return [(id, data["basic_info"]["full_name"]) for id, data in CONSULTANTS.items()]
