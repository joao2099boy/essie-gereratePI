from flask import Flask, render_template, request, jsonify
from weasyprint import HTML, CSS
from supabase import create_client, Client
from datetime import datetime, timezone
from collections import defaultdict

import io
import random
import requests
import urllib.parse
import os
import json
import base64
import calendar

app = Flask(__name__)
application = app

SUPABASE_URL = 'https://aetqpjbeqzmpxwodxykm.supabase.co'
BUCKET_NAME = 'piGeradasPDF'
API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFldHFwamJlcXptcHh3b2R4eWttIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjA0NDY1NDYsImV4cCI6MjAzNjAyMjU0Nn0.lh5g5i-boQZd6Wi_Zgm_JWtAB8s5w47ysP9DEGbdwEA'
AUTHORIZATION = 'Bearer ' + API_KEY

supabase: Client = create_client(SUPABASE_URL, API_KEY)

@app.template_filter('currency')
def currency(value):
    """Formata o valor como moeda."""
    try:
        value = float(value)
        return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return value

def obter_mes_ano_formatado():
    agora_utc = datetime.now(timezone.utc)
    mes_atual = agora_utc.month
    ano_atual = agora_utc.year

    meses = [
        "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
        "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"
    ]

    mes_ano_formatado = f"{meses[mes_atual - 1]}/{ano_atual}"
    return mes_ano_formatado


def calcular_dias_mes(data_inicio_str):
    data_datetime = datetime.strptime(data_inicio_str, "%d/%m/%Y")
    
    ano = data_datetime.year
    mes = data_datetime.month
    
    quantidade_dias = calendar.monthrange(ano, mes)[1]
    return quantidade_dias


def convert_image_to_base64(img_path):
    try:
        with open(img_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Erro ao converter imagem para base64: {e}")
        return None

def upload_to_supabase(pdf_buffer, pdf_name):
    try:
        encoded_pdf_name = urllib.parse.quote(pdf_name)
        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_NAME}/PDFs/{encoded_pdf_name}"
        
        headers = {
            'apikey': API_KEY,
            'Authorization': AUTHORIZATION,
            'Content-Type': 'application/pdf'
        }
        
        response = requests.post(url, headers=headers, data=pdf_buffer.getvalue())

        print(f"Upload URL: {url}")
        print(f"Response Status Code: {response.status_code}")
        print(f"Response Text: {response.text}")

        if response.status_code == 200 or response.status_code == 201:
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/PDFs/{encoded_pdf_name}"
            return public_url
        else:
            return None
    except Exception as e:
        print(f"Erro ao fazer upload para Supabase: {e}")
        return None

def update_database(numberPI, pdf_url, ordem_pi):
    try:
        response = supabase.table('aps_auxiliar').update({
            'url_pdf': pdf_url,
            'ordem_pi': ordem_pi
        }).eq('id', numberPI).execute()
        
        if response.data is None:
            print(f"Erro ao atualizar o banco de dados para PI {numberPI}: {response}")
        else:
            print(f"Banco de dados atualizado com sucesso para PI {numberPI}")
    
    except Exception as error:
        print(f"Erro ao atualizar o banco de dados para PI {numberPI}: {error}")

def convert_image_url_to_base64(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return base64.b64encode(response.content).decode('utf-8')
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar a imagem: {e}")
        return None

def ajustar_numeros_pi(pis):
    # Agrupar PIs por CNPJ
    pis_por_cnpj = defaultdict(list)
    todos_numeros_pi = []

    for pi in pis:
        cnpj = pi.get('VeiculoCNPJ')
        numero = pi.get('numberPI')
        if cnpj and numero:
            pis_por_cnpj[cnpj].append(int(numero))
            todos_numeros_pi.append(int(numero))

    # Encontrar o menor número PI
    menor_numero = min(todos_numeros_pi) if todos_numeros_pi else 0

    # Ajustar números PI
    numeros_ajustados = set()
    
    for i, cnpj in enumerate(pis_por_cnpj.keys()):
        novo_numero = menor_numero + i
        numeros_ajustados.add(novo_numero)

    # Garantir que temos pelo menos dois números
    if len(numeros_ajustados) == 1:
        numeros_ajustados.add(menor_numero + 1)

    # Converter para lista, ordenar e transformar em strings
    numeros_ajustados_lista = [str(num) for num in sorted(numeros_ajustados)]

    return numeros_ajustados_lista

def separar_json(data):
    separated_data = {}
    for item in data:
        for pi in item['PI']:
            cnpj = pi['VeiculoCNPJ']
            if cnpj not in separated_data:
                separated_data[cnpj] = item.copy()
                separated_data[cnpj]['PI'] = []
            separated_data[cnpj]['PI'].append(pi)
    
    return list(separated_data.values())

def generate_pdf(data, numero_pi_ajustado):
    try:
        # Extrair e preparar os dados necessários
        mes_ano_formatado = obter_mes_ano_formatado()
        dias_mes = calcular_dias_mes(data['DataInicio'])
        agencia = data['Agencia']
        assinatura_url = data.get('Assinatura', '')
        logo_url = data['Empresa'].get('logo', '')
        pis = data['PI']
        pecas = [peca for pi in pis for peca in pi['Pecas']]

        def safe_float(value):
            return float(value) if value and value.strip() else 0.0

        def safe_int(value):
            return int(value) if value and value.strip() else 0

        # Determinar o template a ser usado
        var_tipoRenderizado = {
            'Rádio': 'piRadio.html',
            'OOH': 'ooh.html',
            'Impressos': 'impressos.html',
            'Digital': 'digital.html',
            'Carro de Som': 'carro_de_som.html'
        }.get(pis[0]['tipo'], 'impressos.html')

        # Processar dados de datas
        for pi in pis:
            if isinstance(pi.get('datasSelecionadas'), str):
                try:
                    pi['datasSelecionadas'] = json.loads(pi['datasSelecionadas'])
                except json.JSONDecodeError:
                    print(f"Erro ao decodificar JSON em 'datasSelecionadas' para PI {pi['numberPI']}")
                    pi['datasSelecionadas'] = {}
            else:
                pi['datasSelecionadas'] = pi.get('datasSelecionadas', {})

        # Calcular totais
        total_bruto = sum(safe_float(pi['TotalBruto']) for pi in pis)
        total_comissao_agencia = sum(safe_float(pi['comissaoAgencia']) for pi in pis)
        comissao_sbc = sum(safe_float(pi['Comissao']) for pi in pis)
        total_liquido = sum(safe_float(pi['TotalLiquido']) for pi in pis)
        total_unitario_bruto = sum(safe_float(pi['UnitarioBruto']) for pi in pis)
        total_insercoes = sum(safe_int(pi['Insercoes']) for pi in pis)

        nomeEmpresa = data['Empresa']['NomeFantasia']

        # Renderizar o HTML para o PDF
        rendered_html = render_template(
            var_tipoRenderizado,
            logoEmpresa=logo_url,
            nomeAgencia=agencia['NomeFantasia'],
            cidadeAgencia=agencia['Cidade'],
            cnpjAgencia=agencia['CNPJ'],
            estadoAgencia=agencia['Estado'],
            Empresa=data['Empresa'],
            Cliente=data['Cliente'],
            NumeroPI=numero_pi_ajustado,  # Usar o numero_pi_ajustado
            NumeroAP=data['NumeroAP'],
            DataVencimento=data['DataVencimento'],
            DataEmissao=data['DataEmissao'],
            Campanha=data['Campanha'],
            Produto=data['Produto'],
            obsOne=data['obsOne'],
            obsTwo=data['obsTwo'],
            Observacoes=data['Observacoes'],
            Assinatura=assinatura_url,
            MesAno=mes_ano_formatado,
            PI=pis,  # Renderiza apenas o primeiro PI
            pecas=pecas,
            nomeEmpresa = nomeEmpresa,
            TotalLiquido=total_liquido,
            totalBruto=total_bruto,
            comissaoAgencia=total_comissao_agencia,
            comissaoSBC=comissao_sbc,
            totalBrutoo=total_unitario_bruto,
            descontoGeral=total_comissao_agencia,
            totalInsercoes=total_insercoes,
            dias_mes=dias_mes  # Adicionado aqui
        )

        css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/css', 'style.css')

        html = HTML(string=rendered_html)
        document = html.render(stylesheets=[CSS(css_path)])
        page = document.pages[0]
        new_document = document.copy([page])

        pdf = new_document.write_pdf()

        buffer = io.BytesIO(pdf)
        buffer.seek(0)

        return buffer
    
    except Exception as e:
        print(f"Erro ao gerar PDF: {e}")
        return None
    
@app.route('/generate_local_pdfs', methods=['POST'])
def generate_local_pdfs():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    
    separated_data = separar_json(data)
    
    if not separated_data:
        print("Falha ao separar JSON. Dados originais:", json.dumps(data, indent=2))
        return jsonify({"error": "Failed to separate JSON. Check server logs for details."}), 400

    pdf_info = []

    # Ajustar números PI para todos os dados separados
    all_pis = [pi for item in separated_data for pi in item['PI']]
    numeros_pi_ajustados = ajustar_numeros_pi(all_pis)

    for index, item in enumerate(separated_data):
        if index < len(numeros_pi_ajustados):
            numero_pi_ajustado = numeros_pi_ajustados[index]
        else:
            numero_pi_ajustado = numeros_pi_ajustados[-1]
        
        pdf_buffer = generate_pdf(item, numero_pi_ajustado)
        if pdf_buffer is None:
            return jsonify({"error": f"Failed to generate PDF for item {index}"}), 500

        random_number = random.randint(10000000, 99999999)
        pdf_name = f"{random_number}.pdf"
        
        pdf_path = os.path.join('generated_pdfs', pdf_name)
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

        with open(pdf_path, 'wb') as pdf_file:
            pdf_file.write(pdf_buffer.getvalue())

        print(f"PDF salvo em: {pdf_path}")
        pdf_info.append({
            "numberPI": numero_pi_ajustado,
            "pdf_path": pdf_path
        })

    return jsonify({"pdf_info": pdf_info})


@app.route('/generate_pdfs', methods=['POST'])
def generate_pdfs():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    separated_data = separar_json(data)
    
    if not separated_data:
        print("Falha ao separar JSON. Dados originais:", json.dumps(data, indent=2))
        return jsonify({"error": "Failed to separate JSON. Check server logs for details."}), 400

    # Ajustar números PI para todos os dados separados
    all_pis = [pi for item in separated_data for pi in item['PI']]
    numeros_pi_ajustados = ajustar_numeros_pi(all_pis)

    pdf_info = []

    for index, item in enumerate(separated_data):
        print("Processando item:", json.dumps(item, indent=2))

        if index < len(numeros_pi_ajustados):
            numero_pi_ajustado = numeros_pi_ajustados[index]
        else:
            numero_pi_ajustado = numeros_pi_ajustados[-1]

        pdf_buffer = generate_pdf(item, numero_pi_ajustado)
        if pdf_buffer is None:
            return jsonify({"error": f"Failed to generate PDF for item {index}"}), 500

        random_number = random.randint(10000000, 99999999)

        pdf_name = f"{random_number}.pdf"
        encoded_pdf_name = urllib.parse.quote(pdf_name)

        pdf_url = upload_to_supabase(pdf_buffer, encoded_pdf_name)
        
        if pdf_url:
            # Atualizar o banco de dados com o novo número PI ajustado
            for pi in item['PI']:
                update_database(pi['numberPI'], pdf_url, numero_pi_ajustado)
            
            pdf_info.append({
                "numbersPI": ",".join([pi['numberPI'] for pi in item['PI']]),
                "ordem_pi": numero_pi_ajustado,
                "pdf_url": pdf_url
            })
        else:
            return jsonify({"error": "Failed to upload PDF to Supabase"}), 500

    print("PDF Info:", pdf_info)

    return jsonify({"pdf_info": pdf_info})

@app.route('/', methods=['POST', 'GET'])
def index():
    return "Aplicação está Online!"

@app.route('/ajustar_numeros_pi', methods=['POST'])
def route_ajustar_numeros_pi():
    pis = request.json
    pis_separadas = separar_json(pis)
    return ajustar_numeros_pi(pis_separadas)

if __name__ == '__main__':
    app.run(debug=True)