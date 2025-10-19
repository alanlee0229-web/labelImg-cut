import cv2
import numpy as np

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

# 确保QMessageBox可用
if 'QMessageBox' not in dir():
    QMessageBox = QMessageBox

# from PyQt4.QtOpenGL import *

from libs.shape import Shape
from libs.utils import distance

CURSOR_DEFAULT = Qt.ArrowCursor
CURSOR_POINT = Qt.PointingHandCursor
CURSOR_DRAW = Qt.CrossCursor
CURSOR_MOVE = Qt.ClosedHandCursor
CURSOR_GRAB = Qt.OpenHandCursor


# class Canvas(QGLWidget):


class Canvas(QWidget):
    zoomRequest = pyqtSignal(int)
    lightRequest = pyqtSignal(int)
    scrollRequest = pyqtSignal(int, int)
    newShape = pyqtSignal()
    selectionChanged = pyqtSignal(bool)
    shapeMoved = pyqtSignal()
    drawingPolygon = pyqtSignal(bool)

    CREATE, EDIT = list(range(2))

    epsilon = 24.0

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        # Initialise local state.
        self.mode = self.EDIT
        self.shapes = []
        self.current = None
        self.selected_shape = None  # save the selected shape here
        self.selected_shape_copy = None
        self.drawing_line_color = QColor(0, 0, 255)
        self.drawing_rect_color = QColor(0, 0, 255)
        self.line = Shape(line_color=self.drawing_line_color)
        self.prev_point = QPointF()
        self.offsets = QPointF(), QPointF()
        self.scale = 1.0
        self.overlay_color = None
        self.label_font_size = 8
        self.pixmap = QPixmap()
        self.visible = {}
        self._hide_background = False
        self.hide_background = False
        self.h_shape = None
        self.h_vertex = None
        self._painter = QPainter()
        self._cursor = CURSOR_DEFAULT
        # Menus:
        self.menus = (QMenu(), QMenu())
        # Set widget options.
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)
        self.verified = False
        self.draw_square = False
        self.drawing_mode = 'fixed'  # 'fixed' or 'freehand'

        # initialisation for panning
        self.pan_initial_pos = QPoint()

    def set_drawing_color(self, qcolor):
        self.drawing_line_color = qcolor
        self.drawing_rect_color = qcolor

    def enterEvent(self, ev):
        self.override_cursor(self._cursor)

    def leaveEvent(self, ev):
        self.restore_cursor()

    def focusOutEvent(self, ev):
        self.restore_cursor()

    def isVisible(self, shape):
        return self.visible.get(shape, True)

    def drawing(self):
        return self.mode == self.CREATE

    def editing(self):
        return self.mode == self.EDIT

    def set_editing(self, value=True):
        self.mode = self.EDIT if value else self.CREATE
        if not value:  # Create
            self.un_highlight()
            self.de_select_shape()
        self.prev_point = QPointF()
        self.repaint()

    def un_highlight(self, shape=None):
        if shape == None or shape == self.h_shape:
            if self.h_shape:
                self.h_shape.highlight_clear()
            self.h_vertex = self.h_shape = None

    def selected_vertex(self):
        return self.h_vertex is not None

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        pos = self.transform_pos(ev.pos())

        # Update coordinates in status bar if image is opened
        window = self.parent().window()
        if window.file_path is not None:
            self.parent().window().label_coordinates.setText(
                'X: %d; Y: %d' % (pos.x(), pos.y()))

        # Polygon drawing.
        if self.drawing():
            self.override_cursor(CURSOR_DRAW)
            if self.current:
                # Display annotation width and height while drawing
                current_width = abs(self.current[0].x() - pos.x())
                current_height = abs(self.current[0].y() - pos.y())
                self.parent().window().label_coordinates.setText(
                    'Width: %d, Height: %d / X: %d; Y: %d' % (current_width, current_height, pos.x(), pos.y()))

                color = self.drawing_line_color
                if self.out_of_pixmap(pos):
                    # Don't allow the user to draw outside the pixmap.
                    # Clip the coordinates to 0 or max,
                    # if they are outside the range [0, max]
                    size = self.pixmap.size()
                    clipped_x = min(max(0, pos.x()), size.width())
                    clipped_y = min(max(0, pos.y()), size.height())
                    pos = QPointF(clipped_x, clipped_y)
                elif len(self.current) > 1 and self.close_enough(pos, self.current[0]):
                    # Attract line to starting point and colorise to alert the
                    # user:
                    pos = self.current[0]
                    color = self.current.line_color
                    self.override_cursor(CURSOR_POINT)
                    self.current.highlight_vertex(0, Shape.NEAR_VERTEX)

                # 让绘制线条跟随最新点击的坐标，而不是最初的点击坐标
                if self.draw_square:
                    # 如果有多个点，使用最后一个点作为起点
                    if len(self.current) > 1:
                        start_pos = self.current[-1]
                    else:
                        start_pos = self.current[0]
                    min_x = start_pos.x()
                    min_y = start_pos.y()
                    min_size = min(abs(pos.x() - min_x), abs(pos.y() - min_y))
                    direction_x = -1 if pos.x() - min_x < 0 else 1
                    direction_y = -1 if pos.y() - min_y < 0 else 1
                    self.line[0] = start_pos
                    self.line[1] = QPointF(min_x + direction_x * min_size, min_y + direction_y * min_size)
                else:
                    # 如果有多个点，使用最后一个点作为起点
                    if len(self.current) > 1:
                        self.line[0] = self.current[-1]
                    else:
                        self.line[0] = self.current[0]
                    self.line[1] = pos

                self.line.line_color = color
                self.prev_point = QPointF()
                self.current.highlight_clear()
            else:
                self.prev_point = pos
            self.repaint()
            return

        # Polygon copy moving.
        if Qt.RightButton & ev.buttons():
            if self.selected_shape_copy and self.prev_point:
                self.override_cursor(CURSOR_MOVE)
                self.bounded_move_shape(self.selected_shape_copy, pos)
                self.repaint()
            elif self.selected_shape:
                self.selected_shape_copy = self.selected_shape.copy()
                self.repaint()
            return

        # Polygon/Vertex moving.
        if Qt.LeftButton & ev.buttons():
            if self.selected_vertex():
                self.bounded_move_vertex(pos)
                self.shapeMoved.emit()
                self.repaint()

                # Display annotation width and height while moving vertex
                point1 = self.h_shape[1]
                point3 = self.h_shape[3]
                current_width = abs(point1.x() - point3.x())
                current_height = abs(point1.y() - point3.y())
                self.parent().window().label_coordinates.setText(
                    'Width: %d, Height: %d / X: %d; Y: %d' % (current_width, current_height, pos.x(), pos.y()))
            elif self.selected_shape and self.prev_point:
                self.override_cursor(CURSOR_MOVE)
                self.bounded_move_shape(self.selected_shape, pos)
                self.shapeMoved.emit()
                self.repaint()

                # Display annotation width and height while moving shape
                point1 = self.selected_shape[1]
                point3 = self.selected_shape[3]
                current_width = abs(point1.x() - point3.x())
                current_height = abs(point1.y() - point3.y())
                self.parent().window().label_coordinates.setText(
                    'Width: %d, Height: %d / X: %d; Y: %d' % (current_width, current_height, pos.x(), pos.y()))
            else:
                # pan
                delta = ev.pos() - self.pan_initial_pos
                self.scrollRequest.emit(delta.x(), Qt.Horizontal)
                self.scrollRequest.emit(delta.y(), Qt.Vertical)
                self.update()
            return

        # Just hovering over the canvas, 2 possibilities:
        # - Highlight shapes
        # - Highlight vertex
        # Update shape/vertex fill and tooltip value accordingly.
        self.setToolTip("Image")
        priority_list = self.shapes + ([self.selected_shape] if self.selected_shape else [])
        for shape in reversed([s for s in priority_list if self.isVisible(s)]):
            # Look for a nearby vertex to highlight. If that fails,
            # check if we happen to be inside a shape.
            index = shape.nearest_vertex(pos, self.epsilon)
            if index is not None:
                if self.selected_vertex():
                    self.h_shape.highlight_clear()
                self.h_vertex, self.h_shape = index, shape
                shape.highlight_vertex(index, shape.MOVE_VERTEX)
                self.override_cursor(CURSOR_POINT)
                self.setToolTip("Click & drag to move point")
                self.setStatusTip(self.toolTip())
                self.update()
                break
            elif shape.contains_point(pos):
                if self.selected_vertex():
                    self.h_shape.highlight_clear()
                self.h_vertex, self.h_shape = None, shape
                self.setToolTip(
                    "Click & drag to move shape '%s'" % shape.label)
                self.setStatusTip(self.toolTip())
                self.override_cursor(CURSOR_GRAB)
                self.update()

                # Display annotation width and height while hovering inside
                point1 = self.h_shape[1]
                point3 = self.h_shape[3]
                current_width = abs(point1.x() - point3.x())
                current_height = abs(point1.y() - point3.y())
                self.parent().window().label_coordinates.setText(
                    'Width: %d, Height: %d / X: %d; Y: %d' % (current_width, current_height, pos.x(), pos.y()))
                break
        else:  # Nothing found, clear highlights, reset state.
            if self.h_shape:
                self.h_shape.highlight_clear()
                self.update()
            self.h_vertex, self.h_shape = None, None
            self.override_cursor(CURSOR_DEFAULT)

    def mousePressEvent(self, ev):
        pos = self.transform_pos(ev.pos())

        if ev.button() == Qt.LeftButton:
            if self.drawing():
                # 禁用跟随鼠标的正方形显示
                self.draw_square = False
                self.handle_drawing(pos)
            else:
                selection = self.select_shape_point(pos)
                self.prev_point = pos

                if selection is None:
                    # pan
                    QApplication.setOverrideCursor(QCursor(Qt.OpenHandCursor))
                    self.pan_initial_pos = ev.pos()

        elif ev.button() == Qt.RightButton and self.editing():
            self.select_shape_point(pos)
            self.prev_point = pos
        self.update()

    def mouseReleaseEvent(self, ev):
        threshold = float(self.parent().window().fog_threshold_edit.text())
        if ev.button() == Qt.RightButton:
            menu = self.menus[bool(self.selected_shape_copy)]
            self.restore_cursor()
            if not menu.exec_(self.mapToGlobal(ev.pos())) \
                    and self.selected_shape_copy:
                # Cancel the move by deleting the shadow copy.
                self.selected_shape_copy = None
                self.repaint()
        elif ev.button() == Qt.LeftButton and self.selected_shape:
            if self.selected_vertex():
                self.override_cursor(CURSOR_POINT)
                # 获取父类中当前框的坐标
                x0 = self.selected_shape[1].x()
                y0 = self.selected_shape[1].y()
                x1 = self.selected_shape[3].x()
                y1 = self.selected_shape[3].y()
                x = int(min(x0, x1))
                y = int(min(y0, y1))
                w = int(abs(x1 - x0))
                h = int(abs(y1 - y0))
                roi = [x, y, w, h]
                # 加载父类中的图像数据
                image = self.parent().window().image
                # 调用转换方法
                image = self.QImage2CV(image)
                # 调用雾检测函数
                has_fog, ratio = self.detect_fog(image, roi, threshold=threshold)
                # 在父类的fog_result_label中显示结果
                if has_fog:  # 父类显示
                    # 设置字体大小大字体
                    self.parent().window().fog_result_label.setStyleSheet(
                        "QLabel{background-color:white;color:green;font-size:40px;font-weight:bold;border-radius:5px;padding:10px;}")  # 设置为绿色
                    self.parent().window().fog_result_label.setText(f" V/S ratio: {ratio:.2f}")

                else:  # 父类显示
                    self.parent().window().fog_result_label.setStyleSheet(
                        "QLabel{background-color:white;color:red;font-size:40px;font-weight:bold;border-radius:5px;padding:10px;}")  # 设置为红色
                    self.parent().window().fog_result_label.setText(f"V/S ratio: {ratio:.2f}")
            else:
                self.override_cursor(CURSOR_GRAB)
                # 获取父类中当前框的坐标
                x0 = self.selected_shape[1].x()
                y0 = self.selected_shape[1].y()
                x1 = self.selected_shape[3].x()
                y1 = self.selected_shape[3].y()
                x = int(min(x0, x1))
                y = int(min(y0, y1))
                w = int(abs(x1 - x0))
                h = int(abs(y1 - y0))
                roi = [x, y, w, h]
                # 加载父类中的图像数据
                image = self.parent().window().image
                # 调用转换方法
                image = self.QImage2CV(image)
                # 调用雾检测函数
                has_fog, ratio = self.detect_fog(image, roi, threshold=threshold)
                # 在父类的fog_result_label中显示结果
                if has_fog:  # 父类显示
                    # 设置字体大小大字体
                    self.parent().window().fog_result_label.setStyleSheet(
                        "QLabel{background-color:white;color:green;font-size:40px;font-weight:bold;border-radius:5px;padding:10px;}")  # 设置为绿色
                    self.parent().window().fog_result_label.setText(f" V/S ratio: {ratio:.2f}")

                else:  # 父类显示
                    self.parent().window().fog_result_label.setStyleSheet(
                        "QLabel{background-color:white;color:red;font-size:40px;font-weight:bold;border-radius:5px;padding:10px;}")  # 设置为红色
                    self.parent().window().fog_result_label.setText(f"V/S ratio: {ratio:.2f}")
        elif ev.button() == Qt.LeftButton:
            pos = self.transform_pos(ev.pos())
            if self.drawing() and self.current and len(self.current) > 0:
                # 获取 ROI 区域
                x0 = self.current[0].x()
                y0 = self.current[0].y()
                x1 = pos.x()
                y1 = pos.y()
                x = int(min(x0, x1))
                y = int(min(y0, y1))
                w = int(abs(x1 - x0))
                h = int(abs(y1 - y0))
                roi = [x, y, w, h]
                # 加载父类中的图像数据
                image = self.parent().window().image
                # 调用转换方法
                image = self.QImage2CV(image)
                # 调用雾检测函数
                has_fog, ratio = self.detect_fog(image, roi, threshold=threshold)
                # 在父类的fog_result_label中显示结果
                if has_fog:  # 父类显示
                    # 设置字体大小大字体
                    self.parent().window().fog_result_label.setStyleSheet(
                        "QLabel{background-color:white;color:green;font-size:40px;font-weight:bold;border-radius:5px;padding:10px;}")  # 设置为绿色
                    self.parent().window().fog_result_label.setText(f" V/S ratio: {ratio:.2f}")

                else:  # 父类显示
                    self.parent().window().fog_result_label.setStyleSheet(
                        "QLabel{background-color:white;color:red;font-size:40px;font-weight:bold;border-radius:5px;padding:10px;}")  # 设置为红色
                    self.parent().window().fog_result_label.setText(f"V/S ratio: {ratio:.2f}")
                self.handle_drawing(pos)
            else:
                # pan
                QApplication.restoreOverrideCursor()

    def QImage2CV(self, qimg):

        tmp = qimg

        # 使用numpy创建空的图象
        cv_image = np.zeros((tmp.height(), tmp.width(), 3), dtype=np.uint8)

        for row in range(0, tmp.height()):
            for col in range(0, tmp.width()):
                r = qRed(tmp.pixel(col, row))
                g = qGreen(tmp.pixel(col, row))
                b = qBlue(tmp.pixel(col, row))
                cv_image[row, col, 0] = b
                cv_image[row, col, 1] = g
                cv_image[row, col, 2] = r

        return cv_image

    def detect_fog(self, image, roi, threshold=12.0):
        """
        检测图像中是否存在雾。
        :param image: 输入图像（BGR格式）
        :param roi: 感兴趣区域（ROI）的坐标 [x, y, width, height]
        :param threshold: V/S比值的阈值
        :return: 是否存在雾，V/S比值
        """
        x, y, w, h = roi
        roi_image = image[y:y + h, x:x + w]

        if roi_image.size == 0:
            return False, 0.0

        hsv_image = cv2.cvtColor(roi_image, cv2.COLOR_BGR2HSV)
        s = hsv_image[:, :, 1].astype(np.float32)  # 饱和度
        v = hsv_image[:, :, 2].astype(np.float32)  # 亮度

        # 计算饱和度和亮度的均值
        s_avg = np.nanmean(s)
        v_avg = np.nanmean(v)

        with np.errstate(divide='ignore', invalid='ignore'):
            ratio = np.nanmean(v_avg / s_avg)  # 忽略NaN值
            ratio = ratio * 10
        return ratio > threshold, ratio

    def end_move(self, copy=False):
        assert self.selected_shape and self.selected_shape_copy
        shape = self.selected_shape_copy
        # del shape.fill_color
        # del shape.line_color
        if copy:
            self.shapes.append(shape)
            self.selected_shape.selected = False
            self.selected_shape = shape
            self.repaint()
        else:
            self.selected_shape.points = [p for p in shape.points]
        self.selected_shape_copy = None

    def hide_background_shapes(self, value):
        self.hide_background = value
        if self.selected_shape:
            # Only hide other shapes if there is a current selection.
            # Otherwise the user will not be able to select a shape.
            self.set_hiding(True)
            self.repaint()

    def handle_drawing(self, pos):
        if self.current and self.current.reach_max_points() is False:
            # 固定大小模式：创建矩形
            if self.drawing_mode == 'fixed':
                init_pos = self.current.points[0]
                min_x = init_pos.x()
                min_y = init_pos.y()
                
                # 从主窗口获取设置的区块初始大小
                try:
                    main_window = self.parent().window()
                    if hasattr(main_window, 'block_width_edit') and hasattr(main_window, 'block_height_edit'):
                        width = int(main_window.block_width_edit.text())
                        height = int(main_window.block_height_edit.text())
                    else:
                        # 如果没有设置，使用默认值
                        width = 100
                        height = 100
                except (ValueError, AttributeError):
                    # 如果获取失败，使用默认值
                    width = 100
                    height = 100
                
                # 使用设置的宽度和高度
                max_x = min_x + width
                max_y = min_y + height
                
                self.current.add_point(QPointF(max_x, min_y))
                self.current.add_point(QPointF(max_x, max_y))
                self.current.add_point(QPointF(min_x, max_y))
                self.finalise()
            # 自由绘制模式：添加点并等待闭合
            else:  # freehand mode
                # 自由绘制模式下只添加点，不显示固定大小的框框
                # 禁用跟随鼠标的正方形显示
                self.draw_square = False
                # 检查是否靠近起点，如果是则闭合多边形
                if len(self.current.points) > 2 and self.close_enough(pos, self.current.points[0]):
                    self.current.close()
                    self.finalise()
                else:
                    self.current.add_point(pos)
                    # 更新显示当前绘制的线条
                    self.update()
        elif not self.out_of_pixmap(pos):
            self.current = Shape()
            self.current.add_point(pos)
            self.line.points = [pos, pos]
            # 在开始绘制时禁用跟随鼠标的正方形显示
            self.draw_square = False
            self.set_hiding()
            self.drawingPolygon.emit(True)
            self.update()

    def set_hiding(self, enable=True):
        self._hide_background = self.hide_background if enable else False

    def can_close_shape(self):
        return self.drawing() and self.current and len(self.current.points) > 2

    def mouseDoubleClickEvent(self, ev):
        # We need at least 4 points here, since the mousePress handler
        # adds an extra one before this handler is called.
        if self.can_close_shape() and len(self.current) > 3:
            self.current.pop_point()
            self.finalise()

    def select_shape(self, shape):
        self.de_select_shape()
        shape.selected = True
        self.selected_shape = shape
        self.set_hiding()
        self.selectionChanged.emit(True)
        self.update()

    def select_shape_point(self, point):
        """Select the first shape created which contains this point."""
        self.de_select_shape()
        if self.selected_vertex():  # A vertex is marked for selection.
            index, shape = self.h_vertex, self.h_shape
            shape.highlight_vertex(index, shape.MOVE_VERTEX)
            self.select_shape(shape)
            return self.h_vertex
        for shape in reversed(self.shapes):
            if self.isVisible(shape) and shape.contains_point(point):
                self.select_shape(shape)
                self.calculate_offsets(shape, point)
                return self.selected_shape
        return None

    def calculate_offsets(self, shape, point):
        rect = shape.bounding_rect()
        x1 = rect.x() - point.x()
        y1 = rect.y() - point.y()
        x2 = (rect.x() + rect.width()) - point.x()
        y2 = (rect.y() + rect.height()) - point.y()
        self.offsets = QPointF(x1, y1), QPointF(x2, y2)

    def snap_point_to_canvas(self, x, y):
        """
        Moves a point x,y to within the boundaries of the canvas.
        :return: (x,y,snapped) where snapped is True if x or y were changed, False if not.
        """
        if x < 0 or x > self.pixmap.width() or y < 0 or y > self.pixmap.height():
            x = max(x, 0)
            y = max(y, 0)
            x = min(x, self.pixmap.width())
            y = min(y, self.pixmap.height())
            return x, y, True

        return x, y, False

    def bounded_move_vertex(self, pos):
        index, shape = self.h_vertex, self.h_shape
        point = shape[index]
        if self.out_of_pixmap(pos):
            size = self.pixmap.size()
            clipped_x = min(max(0, pos.x()), size.width())
            clipped_y = min(max(0, pos.y()), size.height())
            pos = QPointF(clipped_x, clipped_y)

        if self.draw_square:
            opposite_point_index = (index + 2) % 4
            opposite_point = shape[opposite_point_index]

            min_size = min(abs(pos.x() - opposite_point.x()), abs(pos.y() - opposite_point.y()))
            direction_x = -1 if pos.x() - opposite_point.x() < 0 else 1
            direction_y = -1 if pos.y() - opposite_point.y() < 0 else 1
            shift_pos = QPointF(opposite_point.x() + direction_x * min_size - point.x(),
                                opposite_point.y() + direction_y * min_size - point.y())
        else:
            shift_pos = pos - point

        shape.move_vertex_by(index, shift_pos)

        left_index = (index + 1) % 4
        right_index = (index + 3) % 4
        left_shift = None
        right_shift = None
        if index % 2 == 0:
            right_shift = QPointF(shift_pos.x(), 0)
            left_shift = QPointF(0, shift_pos.y())
        else:
            left_shift = QPointF(shift_pos.x(), 0)
            right_shift = QPointF(0, shift_pos.y())
        shape.move_vertex_by(right_index, right_shift)
        shape.move_vertex_by(left_index, left_shift)

    def bounded_move_shape(self, shape, pos):
        if self.out_of_pixmap(pos):
            return False  # No need to move
        o1 = pos + self.offsets[0]
        if self.out_of_pixmap(o1):
            pos -= QPointF(min(0, o1.x()), min(0, o1.y()))
        o2 = pos + self.offsets[1]
        if self.out_of_pixmap(o2):
            pos += QPointF(min(0, self.pixmap.width() - o2.x()),
                           min(0, self.pixmap.height() - o2.y()))
        # The next line tracks the new position of the cursor
        # relative to the shape, but also results in making it
        # a bit "shaky" when nearing the border and allows it to
        # go outside of the shape's area for some reason. XXX
        # self.calculateOffsets(self.selectedShape, pos)
        dp = pos - self.prev_point
        if dp:
            shape.move_by(dp)
            self.prev_point = pos
            return True
        return False

    def de_select_shape(self):
        if self.selected_shape:
            self.selected_shape.selected = False
            self.selected_shape = None
            self.set_hiding(False)
            self.selectionChanged.emit(False)
            self.update()

    def delete_selected(self):
        if self.selected_shape:
            shape = self.selected_shape
            self.un_highlight(shape)
            self.shapes.remove(self.selected_shape)
            self.selected_shape = None
            self.update()
            return shape

    def copy_selected_shape(self):
        if self.selected_shape:
            shape = self.selected_shape.copy()
            self.de_select_shape()
            self.shapes.append(shape)
            shape.selected = True
            self.selected_shape = shape
            self.bounded_shift_shape(shape)
            return shape

    def bounded_shift_shape(self, shape):
        # Try to move in one direction, and if it fails in another.
        # Give up if both fail.
        point = shape[0]
        offset = QPointF(2.0, 2.0)
        self.calculate_offsets(shape, point)
        self.prev_point = point
        if not self.bounded_move_shape(shape, point - offset):
            self.bounded_move_shape(shape, point + offset)

    def paintEvent(self, event):
        if not self.pixmap:
            return super(Canvas, self).paintEvent(event)

        p = self._painter
        p.begin(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.HighQualityAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        p.scale(self.scale, self.scale)
        p.translate(self.offset_to_center())

        temp = self.pixmap
        if self.overlay_color:
            temp = QPixmap(self.pixmap)
            painter = QPainter(temp)
            painter.setCompositionMode(painter.CompositionMode_Overlay)
            painter.fillRect(temp.rect(), self.overlay_color)
            painter.end()

        p.drawPixmap(0, 0, temp)
        Shape.scale = self.scale
        Shape.label_font_size = self.label_font_size
        for shape in self.shapes:
            if (shape.selected or not self._hide_background) and self.isVisible(shape):
                shape.fill = shape.selected or shape == self.h_shape
                shape.paint(p)
        if self.current:
            self.current.paint(p)
            self.line.paint(p)
        if self.selected_shape_copy:
            self.selected_shape_copy.paint(p)

        # Paint rect
        if self.current is not None and len(self.line) == 2:
            left_top = self.line[0]
            right_bottom = self.line[1]
            rect_width = right_bottom.x() - left_top.x()
            rect_height = right_bottom.y() - left_top.y()
            p.setPen(self.drawing_rect_color)
            brush = QBrush(Qt.BDiagPattern)
            p.setBrush(brush)
            p.drawRect(int(left_top.x()), int(left_top.y()), int(rect_width), int(rect_height))

        if self.drawing() and not self.prev_point.isNull() and not self.out_of_pixmap(self.prev_point):
            p.setPen(QColor(0, 0, 0))
            p.drawLine(int(self.prev_point.x()), 0, int(self.prev_point.x()), int(self.pixmap.height()))
            p.drawLine(0, int(self.prev_point.y()), int(self.pixmap.width()), int(self.prev_point.y()))

        self.setAutoFillBackground(True)
        if self.verified:
            pal = self.palette()
            pal.setColor(self.backgroundRole(), QColor(184, 239, 38, 128))
            self.setPalette(pal)
        else:
            pal = self.palette()
            pal.setColor(self.backgroundRole(), QColor(232, 232, 232, 255))
            self.setPalette(pal)

        p.end()

    def transform_pos(self, point):
        """Convert from widget-logical coordinates to painter-logical coordinates."""
        return point / self.scale - self.offset_to_center()

    def offset_to_center(self):
        s = self.scale
        area = super(Canvas, self).size()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        aw, ah = area.width(), area.height()
        x = (aw - w) / (2 * s) if aw > w else 0
        y = (ah - h) / (2 * s) if ah > h else 0
        return QPointF(x, y)

    def out_of_pixmap(self, p):
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w and 0 <= p.y() <= h)

    def finalise(self):
        """最终确定当前绘制的形状"""
        if not self.current:
            return
        # 验证形状点数量 - 至少需要3个点形成多边形
        if len(self.current.points) < 3:
            return
            
        # 检查是否首尾点相同，如果是则移除最后一点再闭合
        if self.current.points[0] == self.current.points[-1]:
            self.current.points.pop()
        
        # 关闭多边形
        self.current.close()
        # 添加到形状列表
        self.shapes.append(self.current)
        # 清除当前形状
        self.current = None
        # 恢复背景显示
        self.set_hiding(False)
        # 发送新建形状信号
        self.newShape.emit()
        # 通知绘制多边形已结束
        self.drawingPolygon.emit(False)
        # 更新显示
        self.update()
        # 通知父窗口添加标签
        if hasattr(self, 'parent') and self.parent and hasattr(self.parent, 'add_label'):
            self.parent.add_label(self.shapes[-1])

    def close_enough(self, p1, p2):
        # d = distance(p1 - p2)
        # m = (p1-p2).manhattanLength()
        # print "d %.2f, m %d, %.2f" % (d, m, d - m)
        return distance(p1 - p2) < self.epsilon

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        if self.pixmap:
            return self.scale * self.pixmap.size()
        return super(Canvas, self).minimumSizeHint()

    def wheelEvent(self, ev):
        qt_version = 4 if hasattr(ev, "delta") else 5
        if qt_version == 4:
            if ev.orientation() == Qt.Vertical:
                v_delta = ev.delta()
                h_delta = 0
            else:
                h_delta = ev.delta()
                v_delta = 0
        else:
            delta = ev.angleDelta()
            h_delta = delta.x()
            v_delta = delta.y()

        mods = ev.modifiers()
        if int(Qt.ControlModifier) | int(Qt.ShiftModifier) == int(mods) and v_delta:
            self.lightRequest.emit(v_delta)
        elif Qt.ControlModifier == int(mods) and v_delta:
            self.zoomRequest.emit(v_delta)
        else:
            v_delta and self.scrollRequest.emit(v_delta, Qt.Vertical)
            h_delta and self.scrollRequest.emit(h_delta, Qt.Horizontal)
        ev.accept()

    def keyPressEvent(self, ev):
        key = ev.key()
        if key == Qt.Key_Escape and self.current:
            print('ESC press')
            self.current = None
            self.drawingPolygon.emit(False)
            self.update()
        elif key == Qt.Key_Return and self.can_close_shape():
            self.finalise()
        elif key == Qt.Key_Left and self.selected_shape:
            self.move_one_pixel('Left')
        elif key == Qt.Key_Right and self.selected_shape:
            self.move_one_pixel('Right')
        elif key == Qt.Key_Up and self.selected_shape:
            self.move_one_pixel('Up')
        elif key == Qt.Key_Down and self.selected_shape:
            self.move_one_pixel('Down')
        # 添加c键快捷键：切割检测框
        elif key == Qt.Key_C and not self.drawing() and self.selected_shape:
            # 获取主窗口并调用切割方法
            try:
                # 尝试向上查找主窗口
                parent = self.parent()
                while parent and not hasattr(parent, 'cut_selected_bbox'):
                    parent = parent.parent()
                
                if parent and hasattr(parent, 'cut_selected_bbox'):
                    parent.cut_selected_bbox()
            except Exception as e:
                print(f"Error calling cut_selected_bbox: {e}")
        # 添加q键快捷键：切换到固定尺寸模式
        elif key == Qt.Key_Q:
            self.drawing_mode = 'fixed'
            # 显示提示框
            QMessageBox.information(None, "模式切换", "已切换到固定区块Q模式")
        # 添加e键快捷键：切换到不规则尺寸模式
        elif key == Qt.Key_E:
            self.drawing_mode = 'freehand'
            # 显示提示框
            QMessageBox.information(None, "模式切换", "已切换到自定义选区E模式")

    def move_one_pixel(self, direction):
        # print(self.selectedShape.points)
        if direction == 'Left' and not self.move_out_of_bound(QPointF(-1.0, 0)):
            # print("move Left one pixel")
            self.selected_shape.points[0] += QPointF(-1.0, 0)
            self.selected_shape.points[1] += QPointF(-1.0, 0)
            self.selected_shape.points[2] += QPointF(-1.0, 0)
            self.selected_shape.points[3] += QPointF(-1.0, 0)
        elif direction == 'Right' and not self.move_out_of_bound(QPointF(1.0, 0)):
            # print("move Right one pixel")
            self.selected_shape.points[0] += QPointF(1.0, 0)
            self.selected_shape.points[1] += QPointF(1.0, 0)
            self.selected_shape.points[2] += QPointF(1.0, 0)
            self.selected_shape.points[3] += QPointF(1.0, 0)
        elif direction == 'Up' and not self.move_out_of_bound(QPointF(0, -1.0)):
            # print("move Up one pixel")
            self.selected_shape.points[0] += QPointF(0, -1.0)
            self.selected_shape.points[1] += QPointF(0, -1.0)
            self.selected_shape.points[2] += QPointF(0, -1.0)
            self.selected_shape.points[3] += QPointF(0, -1.0)
        elif direction == 'Down' and not self.move_out_of_bound(QPointF(0, 1.0)):
            # print("move Down one pixel")
            self.selected_shape.points[0] += QPointF(0, 1.0)
            self.selected_shape.points[1] += QPointF(0, 1.0)
            self.selected_shape.points[2] += QPointF(0, 1.0)
            self.selected_shape.points[3] += QPointF(0, 1.0)
        self.shapeMoved.emit()
        self.repaint()

    def move_out_of_bound(self, step):
        points = [p1 + p2 for p1, p2 in zip(self.selected_shape.points, [step] * 4)]
        return True in map(self.out_of_pixmap, points)

    def set_last_label(self, text, line_color=None, fill_color=None):
        assert text
        self.shapes[-1].label = text
        if line_color:
            self.shapes[-1].line_color = line_color

        if fill_color:
            self.shapes[-1].fill_color = fill_color

        return self.shapes[-1]

    def undo_last_line(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.set_open()
        self.line.points = [self.current[-1], self.current[0]]
        self.drawingPolygon.emit(True)

    def reset_all_lines(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.set_open()
        self.line.points = [self.current[-1], self.current[0]]
        self.drawingPolygon.emit(True)
        self.current = None
        self.drawingPolygon.emit(False)
        self.update()

    def load_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.shapes = []
        self.repaint()

    def load_shapes(self, shapes):
        self.shapes = list(shapes)
        self.current = None
        self.repaint()

    def set_shape_visible(self, shape, value):
        self.visible[shape] = value
        self.repaint()

    def current_cursor(self):
        cursor = QApplication.overrideCursor()
        if cursor is not None:
            cursor = cursor.shape()
        return cursor

    def override_cursor(self, cursor):
        self._cursor = cursor
        if self.current_cursor() is None:
            QApplication.setOverrideCursor(cursor)
        else:
            QApplication.changeOverrideCursor(cursor)

    def restore_cursor(self):
        QApplication.restoreOverrideCursor()

    def reset_state(self):
        self.de_select_shape()
        self.un_highlight()
        self.selected_shape_copy = None

        self.restore_cursor()
        self.pixmap = None
        self.update()

    def set_drawing_shape_to_square(self, status):
        self.draw_square = status
        
    def set_drawing_mode(self, mode):
        """设置绘制模式：'fixed'（固定大小矩形）或'freehand'（自由多边形）"""
        self.drawing_mode = mode
