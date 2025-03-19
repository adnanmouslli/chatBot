# dialog_server.py
import asyncio
import websockets
import json
import random
from datetime import datetime, timedelta
import json
import time

class DialogNode:
    def __init__(self, message, options=None, conditions=None):
        self.message = message
        self.options = options or []
        self.conditions = conditions or {}
        self.last_visited = None

class SmartDialogSystem:
    def __init__(self, dialog_file):
        """Initialize the dialog system with a JSON file path"""
        self.dialog_data = self.load_dialog_data(dialog_file)
        self.dialog_tree = self._initialize_dialog_tree()
        self.current_node = 'start'
        self.dialog_history = []
        self.user_context = {
            'name': None,
            'preferences': {},
            'visit_count': 0,
            'last_visit': None
        }
        self.session_start_time = datetime.now()
        self.last_interaction_time = datetime.now()

    def load_dialog_data(self, file_path):
        """Load dialog data from JSON file with error handling"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                # Validate required structure
                if not all(key in data for key in ['nodes', 'greetings', 'responses']):
                    raise ValueError("JSON file missing required sections: nodes, greetings, responses")
                return data
        except FileNotFoundError:
            raise FileNotFoundError(f"Dialog data file '{file_path}' not found")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format in '{file_path}'")
        except Exception as e:
            raise Exception(f"Error loading dialog data: {str(e)}")

    def _initialize_dialog_tree(self):
        """Initialize dialog tree from loaded JSON data"""
        dialog_tree = {}
        try:
            for node_id, node_data in self.dialog_data['nodes'].items():
                if 'message' not in node_data or 'options' not in node_data:
                    raise ValueError(f"Invalid node structure in node {node_id}")
                dialog_tree[node_id] = DialogNode(
                    message=node_data['message'],
                    options=node_data['options']
                )
            return dialog_tree
        except Exception as e:
            raise ValueError(f"Error initializing dialog tree: {str(e)}")

    def get_greeting(self):
        """Generate customized greeting from JSON data"""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            greeting_type = 'morning'
        elif 12 <= hour < 17:
            greeting_type = 'afternoon'
        else:
            greeting_type = 'evening'
            
        return random.choice(self.dialog_data['greetings'][greeting_type])

    def get_random_response(self):
        """Get random response from JSON data"""
        return random.choice(self.dialog_data['responses'])


    def process_interaction(self, user_input):
        """Process user interaction with improved error handling"""
        current_time = datetime.now()
        time_since_last = (current_time - self.last_interaction_time).seconds

        if not user_input.strip():
            return {
                'type': 'error',
                'message': "لم أتمكن من فهم المدخل الفارغ. يرجى المحاولة مجددًا."
            }

        if self.current_node not in self.dialog_tree:
            self.current_node = 'start'
            return self.start_dialog()

        node = self.dialog_tree[self.current_node]
        
        self.dialog_history.append({
            'node': self.current_node,
            'input': user_input,
            'timestamp': current_time,
            'response_time': time_since_last
        })
        
        # Handle special commands
        if user_input.lower() == 'restart':
            self.current_node = 'start'
            return self.start_dialog()
            
        # Process user input
        next_node = None
        for option in node.options:
            if option['id'].lower() == user_input.lower():  # Case-insensitive comparison
                next_node = option['next']
                break

        if next_node and next_node in self.dialog_tree:
            self.current_node = next_node
            node = self.dialog_tree[next_node]
            response = {
                'type': 'node',
                'message': node.message,
                'options': node.options,
                'context': self.get_context_info()
            }
        else:
            response = {
                'type': 'error',
                'message': "عذراً، لم أفهم اختيارك. هل يمكنك التوضيح؟ 🤔",
                'options': node.options
            }
        
        self.last_interaction_time = current_time
        return response
    
    def get_context_info(self):
        """Get current context information"""
        return {
            'visit_count': self.user_context['visit_count'],
            'session_duration': (datetime.now() - self.session_start_time).seconds,
            'last_interaction_delay': (datetime.now() - self.last_interaction_time).seconds
        }

    def start_dialog(self):
        """Start or restart the dialog"""
        self.user_context['visit_count'] += 1
        self.user_context['last_visit'] = datetime.now()
        
        greeting = self.get_greeting()
        start_node = self.dialog_tree.get('start')
        
        if not start_node:
            return {
                'type': 'error',
                'message': "خطأ: لم يتم تهيئة نظام الحوار بشكل صحيح.",
                'options': []
            }
            
        start_message = f"{greeting}\n\nكيف يمكنني مساعدتك اليوم؟"
        
        return {
            'type': 'start',
            'message': start_message,
            'options': start_node.options
        }


class DialogServer:
    def __init__(self):
        dialog_file = r"C:\Users\ADNAN\Desktop\مشاريع تخرج\مشروع الصيدلية الذكية\chatBot\dialog_data.json"
        self.dialog_system = SmartDialogSystem(dialog_file)
        self.active_sessions = {}
        # تعريف الأوقات بالثواني
        self.INACTIVITY_WARNING_TIME = 60  # تحذير بعد دقيقة
        self.INACTIVITY_TIMEOUT_TIME = 180  # إنهاء الجلسة بعد 3 دقائق
        self.ACTIVITY_CHECK_INTERVAL = 20   # فحص النشاط كل 20 ثانية

    async def handle_client(self, websocket):
        session_id = id(websocket)
        self.active_sessions[session_id] = {
            'dialog_system': self.dialog_system,
            'last_activity': datetime.now(),
            'warning_sent': False  # لتجنب إرسال تحذيرات متكررة
        }

        try:
            initial_response = self.dialog_system.start_dialog()
            await websocket.send(json.dumps(initial_response))

            # بدء مراقبة نشاط المستخدم
            monitor_task = asyncio.create_task(
                self.monitor_user_activity(websocket, session_id)
            )

            async for message in websocket:
                try:
                    data = json.loads(message)
                    user_input = data.get('input')
                    print(user_input)
                    
                    if user_input:
                        # تحديث وقت آخر نشاط وإعادة تعيين حالة التحذير
                        self.active_sessions[session_id]['last_activity'] = datetime.now()
                        self.active_sessions[session_id]['warning_sent'] = False
                        
                        response = self.dialog_system.process_interaction(user_input)
                        await websocket.send(json.dumps(response))
                    else:
                        error_response = {
                            'type': 'error',
                            'message': 'المدخل فارغ. يرجى إدخال نص.'
                        }
                        await websocket.send(json.dumps(error_response))

                except json.JSONDecodeError:
                    error_response = {
                        'type': 'error',
                        'message': 'تنسيق رسالة غير صحيح.'
                    }
                    await websocket.send(json.dumps(error_response))

        except websockets.exceptions.ConnectionClosed as e:
            print(f"تم قطع اتصال العميل: {session_id}, السبب: {e.reason}")
        finally:
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            monitor_task.cancel()  # إلغاء مهمة المراقبة عند إغلاق الاتصال

    async def monitor_user_activity(self, websocket, session_id):
        """مراقبة نشاط المستخدم مع تحسين التوقيت والتحكم في التحذيرات"""
        try:
            while session_id in self.active_sessions:
                await asyncio.sleep(self.ACTIVITY_CHECK_INTERVAL)
                
                if session_id not in self.active_sessions:
                    break

                session = self.active_sessions[session_id]
                time_since_last = (datetime.now() - session['last_activity']).seconds

                # إرسال تحذير بعد فترة عدم النشاط
                if time_since_last >= self.INACTIVITY_WARNING_TIME and not session['warning_sent']:
                    try:
                        warning_message = {
                            'type': 'warning',
                            'message': 'يبدو أنك لم ترد منذ فترة. هل تحتاج إلى مساعدة؟'
                        }
                        await websocket.send(json.dumps(warning_message))
                        session['warning_sent'] = True
                    except websockets.exceptions.ConnectionClosed:
                        break

                # إنهاء الجلسة بعد تجاوز وقت الانتظار
                if time_since_last >= self.INACTIVITY_TIMEOUT_TIME:
                    try:
                        timeout_message = {
                            'type': 'timeout',
                            'message': 'تم إنهاء الجلسة بسبب عدم النشاط. يمكنك البدء مجددًا بإرسال رسالة جديدة.'
                        }
                        await websocket.send(json.dumps(timeout_message))
                        if session_id in self.active_sessions:
                            del self.active_sessions[session_id]
                        break
                    except websockets.exceptions.ConnectionClosed:
                        break

        except asyncio.CancelledError:
            # التنظيف عند إلغاء المهمة
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
        except Exception as e:
            print(f"خطأ في مراقبة نشاط المستخدم: {str(e)}")
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]


async def main():
    dialog_server = DialogServer()
    
    server = await websockets.serve(
        dialog_server.handle_client,
        "localhost",
        8765 
    )
    
    print("Dialog server started on ws://localhost:8765")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())