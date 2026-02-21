import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def _check_tesseract_available():
    """检查Tesseract是否可用"""
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')
        version = pytesseract.get_tesseract_version()
        return True, version
    except Exception as e:
        logger.warning(f"Tesseract不可用: {str(e)}")
        return False, str(e)

def process_image_with_tesseract(filepath):
    """
    使用Tesseract OCR提取图片中的文字
    :param filepath: 图片路径
    :return: (success: bool, content: str)
    """
    try:
        from PIL import Image
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

        logger.info(f"使用Tesseract OCR处理图片: {filepath}")
        image = Image.open(filepath)

        if image.mode == 'RGBA':
            image = image.convert('RGB')

        text = pytesseract.image_to_string(image, lang='chi_sim+eng')

        if not text or not text.strip():
            return False, "未检测到文字内容"

        logger.info(f"Tesseract OCR提取成功，文字长度: {len(text)}")
        return True, text.strip()

    except Exception as e:
        logger.error(f"Tesseract OCR处理失败: {str(e)}")
        return False, f"OCR处理失败: {str(e)}"


def process_image_with_easyocr(filepath):
    """
    使用EasyOCR提取图片中的文字（支持更多语言）
    :param filepath: 图片路径
    :return: (success: bool, content: str)
    """
    try:
        import easyocr

        logger.info(f"使用EasyOCR处理图片: {filepath}")

        reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
        results = reader.readtext(filepath)

        if not results:
            return False, "未检测到文字内容"

        text_lines = []
        for bbox, text, confidence in results:
            if confidence > 0.3:
                text_lines.append(text)

        content = '\n'.join(text_lines)
        if not content.strip():
            return False, "未检测到足够置信度的文字"

        logger.info(f"EasyOCR提取成功，文字长度: {len(content)}")
        return True, content

    except ImportError:
        logger.warning("EasyOCR未安装")
        return False, "EasyOCR未安装，请运行: pip install easyocr"
    except Exception as e:
        logger.error(f"EasyOCR处理失败: {str(e)}")
        return False, f"OCR处理失败: {str(e)}"


def process_image(filepath):
    """
    统一图片处理接口（自动选择可用方案）
    :param filepath: 图片路径
    :return: (success: bool, content: str)
    """
    from config import MAX_TEXT_LENGTH

    if not os.path.exists(filepath):
        return False, "文件不存在"

    ext = os.path.splitext(filepath)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
        return False, f"不支持的图片格式: {ext}"

    file_size = os.path.getsize(filepath)
    if file_size > 50 * 1024 * 1024:
        return False, "图片过大（超过50MB）"

    logger.info(f"开始处理图片: {filepath}")

    available, info = _check_tesseract_available()
    if available:
        success, content = process_image_with_tesseract(filepath)
        if success:
            if len(content) > MAX_TEXT_LENGTH:
                content = content[:MAX_TEXT_LENGTH] + "\n（文本过长，已截断）"
            return True, content
        logger.warning(f"Tesseract失败，尝试EasyOCR: {content}")

    success, content = process_image_with_easyocr(filepath)
    if success:
        if len(content) > MAX_TEXT_LENGTH:
            content = content[:MAX_TEXT_LENGTH] + "\n（文本过长，已截断）"
        return True, content

    return False, "所有OCR方案均失败，请安装Tesseract或EasyOCR"


def process_image_with_ai_description(filepath):
    """
    使用AI模型理解图片内容（不仅是OCR，还包括场景描述）
    需要配合多模态模型使用，如BLIP或Qwen-VL
    :param filepath: 图片路径
    :return: (success: bool, content: str)
    """
    try:
        from transformers import AutoProcessor, AutoModelForVision2Seq
        from PIL import Image
        import torch

        logger.info(f"使用AI多模态模型理解图片: {filepath}")

        model_name = os.getenv('VISION_MODEL', 'Salesforce/blip2-opt-2.7b')
        processor = AutoProcessor.from_pretrained(model_name)
        model = AutoModelForVision2Seq.from_pretrained(model_name)

        image = Image.open(filepath).convert('RGB')

        prompt = "Describe this image in detail."
        inputs = processor(images=image, text=prompt, return_tensors="pt")

        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=300,
                do_sample=False
            )

        generated_text = processor.batch_decode(
            generated_ids,
            skip_special_tokens=True
        )[0]

        logger.info(f"AI图片理解成功，长度: {len(generated_text)}")
        return True, generated_text

    except ImportError:
        return False, "transformers未安装"
    except Exception as e:
        logger.error(f"AI图片理解失败: {str(e)}")
        return False, f"处理失败: {str(e)}"
