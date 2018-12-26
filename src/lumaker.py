#-*- using:utf-8 -*-
import collections
import logging
import os
import pickle
import sys
import time

import fiona
from shapely import geometry, ops
# import numpy as np

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# base_dir = "C:/ICP/qgis/projects/"
base_dir = "C:/qgis/ICP/qgis/projects/"
# base_dir = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/"


# new_link_file = "minato-ku/minato-link-new.shp"
# new_link_file = "ohta-ku/road_link_ohta-ku_new.shp"
new_link_file = "/tokyo/road_link_tokyo_new.shp"

# link_file = "minato-ku/minato-link.shp"
link_file = "tokyo/road_link_tokyo.shp"
# link_file = "ohta-ku/road_link_ohta-ku.shp"

# node_file = "minato-ku/minato-node.shp"
node_file = "tokyo/road_node_tokyo.shp"
# node_file = "ohta-ku/road_node_ohta-ku.shp"

new_link_path = base_dir + new_link_file
link_path = base_dir + link_file
node_path = base_dir + node_file

# new objectid 30,000,000からスタート
new_id = 30000000

# cache dir
PICKLE_FILE_DIR = base_dir + "cache/"

from_node_links = {}
to_node_links = {}
newlinks = collections.deque()
all_nodes = collections.deque()

# リンク接合時に値が同一であるべき属性
checkAttributes = ('roadcls_c', 'navicls_c', 'linkcls_c', 'width_c', 'nopass_c', 'oneway_c', 'lane_count',
                   'ts_drm_tri', 'legal_spee', 'legal_sp_1')


# 属性の値が同一かチェック
def check_attributes(f, t, attributes):
    if f is None or t is None:
        return False

    for attr in attributes:
        if f['properties'][attr] != t['properties'][attr]:
            return False
        else:
            return True


# リンクを逆向きに
def reverse_link(link):

    # 一方通行種別 正方向1,3 <=> 逆方向2,4
    if link['properties']['oneway_c'] == 1:
        link['properties']['oneway_c'] = 3
    elif link['properties']['oneway_c'] == 3:
        link['properties']['oneway_c'] = 1
    elif link['properties']['oneway_c'] == 2:
        link['properties']['oneway_c'] = 4
    elif link['properties']['oneway_c'] == 4:
        link['properties']['oneway_c'] = 2

    # リンク方向コード 1:正方向 2:逆方向
    if link['properties']['linkdir_c'] == 1:
        link['properties']['linkdir_c'] = 2
    elif link['properties']['linkdir_c'] == 2:
        link['properties']['linkdir_c'] = 1

    # coordinates listを逆順に
    link['properties']['coordinates'] = link['properties']['coordinates'][::-1]

    return link


def flatten(nested_list):
    # フラットなリストとフリンジを用意
    flat_list = []
    fringe = [nested_list]
    while len(fringe) > 0:
        node = fringe.pop(0)
        # ノードがリストであれば子要素をフリンジに追加
        # リストでなければそのままフラットリストに追加
        if isinstance(node, list):
            fringe = node + fringe
        else:
            flat_list.append(node)

    return flat_list


# ジオメトリLineStringを結合し、MultiLineStringにする
def merge_linestrings(first, second):

    new_coordinates = []

    first_geometry = first['geometry']
    second_geometry = second['geometry']

    f_lines = []
    if first_geometry['type'] == 'MultiLineString':
        first = geometry.MultiLineString(first_geometry['coordinates'])
        for f in first:
            f_lines.append(f)
        # f_lines = ops.linemerge(first)
    else:
        f_lines.append(geometry.LineString(first_geometry['coordinates']))

    if second_geometry['type'] == 'MultiLineString':
        second =  geometry.MultiLineString(second_geometry['coordinates'])
        for s in second:
            f_lines.append(s)
        # s_lines = ops.linemerge(second)
    else:
        f_lines.append(geometry.LineString(second_geometry['coordinates']))

    merged_multiline = geometry.MultiLineString(f_lines)
    linestring = ops.linemerge(merged_multiline)
    return linestring
    # if first_geometry['type'] == 'MultiLineString' or second_geometry['type'] == 'MultiLineString':
    #     if first_geometry['type'] == 'LineString':
    #         new_coordinates.append([first_geometry['coordinates']])
    #     else:
    #         new_coordinates.extend(first_geometry['coordinates'])
    #
    #     if second_geometry['type'] == 'LineString':
    #         new_coordinates.append([second_geometry['coordinates']])
    #     else:
    #         new_coordinates.append(second_geometry['coordinates'])
    # else:
    #     new_coordinates.extend(first_geometry['coordinates'])
    #     new_coordinates.extend(second_geometry['coordinates'])
    #
    # return new_coordinates


# リンクを接合
def merge_links(a, b, node):

    # 新しいobjectid
    global new_id
    multi = False
    # if a['geometry']['type'] == 'MultiLineString':
    #     multi = True
    # print(a)
    # if b['geometry']['type'] == 'MultiLineString':
    #     multi = True
    # print(b)

    # ノードの位置を特定
    aNodes = (a['properties']['fromnodeid'], a['properties']['tonodeid'])
    bNodes = (b['properties']['fromnodeid'], b['properties']['tonodeid'])
    aNodePos = aNodes.index(node)
    bNodePos = bNodes.index(node)

    # coordinates
    newc = []

    # 両リンクの向きを確認 同一方向に
    # <-a- n -b->  =>  -a-> n -b->
    if aNodePos == 0 and bNodePos == 0:
        a = reverse_link(a)
        bc.reverse()
        # shape
        newc = merge_linestrings(b, a)
        # from, to
        newfromnodeid = aNodes[1]
        newtonodeid = bNodes[1]

    # -a-> n -b->  or <-b- n <-a- =>  keep
    elif aNodePos == 1 and bNodePos == 0:
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[1]
        newc = merge_linestrings(a, b)
    # <-a- n <-b- => or -b-> n -a-> keep
    elif aNodePos == 0 and bNodePos == 1:
        newfromnodeid = bNodes[0]
        newtonodeid = aNodes[1]
        newc = merge_linestrings(b, a)
    # -a-> n <-b-  =>  -a-> n -b->
    elif aNodePos == 1 and bNodePos == 1:
        b = reverse_link(b)
        bc.reverse()
        # shape
        newc = merge_linestrings(a, b)
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[0]
    new_id = new_id + 1
    a['properties']['objectid'] = new_id
    a['properties']['fromnodeid'] = newfromnodeid
    a['properties']['tonodeid'] = newtonodeid
    a['geometry'] = geometry.mapping(newc)
    if multi:
        a['geometry']['type'] = "MultiLineString"
        # a['geometry']['coordinates'] = flatten(newc)
    return a


def get_link(node):
    # 接合対象のリンクを特定し、辞書から削除
    if node in from_node_links.keys():
        f = from_node_links.pop(node)
        # print(f"fromlink:{fromlink}")
        if node in to_node_links.keys():
            t = to_node_links.pop(node)
            return f, t
    return None, None


def remove_link(f, t):
    global newlinks
    newlinks = [x for x in newlinks if not x in (f, t)]


# pickleにキャシュとして保存
def save_cache(path, cache):
    try:
        with open(path, 'wb') as f:
            print(f'  Saving pickle file ({path}.pickle)')
            pickle.dump(cache, f)
    except PermissionError as e:
        print(f'Permission Error. skipped {path}.pickle. {e} ')


# pickleから読み込み
def load_cache(path):
    with open(path, 'rb') as f:
        try:
            return pickle.load(f)
        except PermissionError as e:
            print(f'Permission Error when loading cache: {path} {e}')


def main():

    global newlinks, from_node_links, to_node_links
    all_link_count = 0
    merged_link_count = 0

    # リンクレイヤからfromnodeid, tonodeid を取得し、Dict[objectid] 形式で辞書化　
    with fiona.open(link_path, "r") as fl:
        schema = fl.schema.copy()
        print('reading nodes and links')
        pickle_path = os.path.join(PICKLE_FILE_DIR, link_file + ".pickle")
        if os.path.exists(pickle_path):
            # キャッシュあれば読み込み
            print(f'Found pickle file ({os.path.basename(pickle_path)}). loading..')
            crossing_nodes, from_node_links, to_node_links = load_cache(pickle_path)
        else:
            for feature in fl:
                all_nodes.append(feature['properties']['fromnodeid'])
                all_nodes.append(feature['properties']['tonodeid'])
                from_node_id = feature['properties']['fromnodeid']
                from_node_links[from_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
                to_node_id = feature['properties']['tonodeid']
                to_node_links[to_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
                all_link_count = all_link_count + 1

            # 2つのリンクが接続されているノードのobjectid属性を抽出
            c = collections.Counter(all_nodes)
            crossing_nodes = [k for k, v in c.items() if v == 2]
            save_cache(pickle_path, (crossing_nodes, from_node_links, to_node_links))

        print('start merging')
        # connlink=2のノードに接続しているリンクを接合する
        with fiona.open(node_path, "r") as fn:
            with fiona.open(new_link_path, 'w', **fl.meta) as f:
                for feature in fn:
                    nodeid = feature['properties']['objectid']
                    if nodeid in crossing_nodes:
                        nodeid = feature['properties']['objectid']
                        from_link, to_link = get_link(nodeid)
                        if check_attributes(from_link, to_link, checkAttributes):
                            remove_link(from_link, to_link)
                            newlink = merge_links(from_link, to_link, nodeid)
                            newlinks.append(newlink)
                            new_from_node_id = newlink['properties']['fromnodeid']
                            new_to_node_id = newlink['properties']['tonodeid']
                            from_node_links[new_from_node_id] = newlink
                            to_node_links[new_to_node_id] = newlink
                            merged_link_count = merged_link_count + 1
                            # print(f"  tolink:{tolink}")
                            # print(f" newlink:{newlink}")
                            # if merged_link_count == 500:
                            #     exit()
                try:
                    print('start writing')
                    # f.writerecords(newlinks)
                    for r in newlinks:
                        # print(r)
                        f.write(r)

                except Exception as e:
                    logging.exception(f"Error writing :{e}")

                print(f"Finished.  All Links counts: {all_link_count}, Generated LUs: {merged_link_count}")

# tokyo elapsed_time: 10814.245[sec]
if __name__ == '__main__':
    start = time.time()
    main()
    elapsed_time = time.time() - start
    print("elapsed_time: {:.3f}".format(elapsed_time) + "[sec]")

